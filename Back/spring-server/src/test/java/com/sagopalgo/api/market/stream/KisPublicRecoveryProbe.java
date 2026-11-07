package com.sagopalgo.api.market.stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.MarketStreamProperties;
import java.io.IOException;
import java.math.BigInteger;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Clock;
import java.time.DayOfWeek;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpMethod;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

/** Manual test-classpath entry point for a bounded public KRX data probe. */
public final class KisPublicRecoveryProbe {
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final String KIS_ORIGIN = "https://openapi.koreainvestment.com:9443";
    private static final String KEY = "SAGOPALGO_KIS_APP_KEY";
    private static final String SECRET = "SAGOPALGO_KIS_APP_SECRET";
    private static final String STREAM_ENABLED = "SAGOPALGO_MARKET_STREAM_ENABLED";
    private static final int HARD_LIMIT_SECONDS = 110;
    private static final int MAX_FRAME_BYTES = 8 * 1024 * 1024;
    private static final int MAX_EVENTS = 12_000;
    private static final ObjectMapper JSON = new ObjectMapper().findAndRegisterModules()
        .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

    record Observation(long generation, String frameSha256, String publicFrame, Instant receivedAt,
                       List<String> eventIds) {}
    record Phase(long generation, long readySequence, MarketStreamEvent trade, MarketStreamEvent quote) {}
    record VolumeBoundary(String status, String lastBeforeEventId, String firstAfterEventId, String unobservedVolume) {}
    record Result(String schemaVersion, String source, String status, String failureCode, String stockCode,
                  Instant faultInjectedAt, Phase before, Phase after, int approvals, int tunnelArrivals,
                  int upstreamDials, int arrivalsAtStop, int dialsAtStop, int uniqueEvents, int duplicates,
                  int beforeFrames, int afterFrames, boolean stableResetObserved, VolumeBoundary volumeBoundary,
                  KisStreamConnection.RecoverySnapshot stopped, boolean journalCleanEnd, boolean usableForTrading) {}

    static void requireWindow(LocalDate requested, Clock clock) {
        var korea = clock.instant().atZone(SEOUL);
        if (!requested.equals(korea.toLocalDate()) || korea.getDayOfWeek().getValue() >= DayOfWeek.SATURDAY.getValue()
            || korea.toLocalTime().isBefore(LocalTime.of(9, 5)) || !korea.toLocalTime().isBefore(LocalTime.of(15, 17))) {
            throw new IllegalArgumentException("OUTSIDE_CONFIRMED_KRX_WINDOW");
        }
    }

    static Result run(Path directory, String stock, URI upstream, KisMarketProperties kis, RestClient rest,
                      Clock clock, KisStreamConnection.Timing timing, Duration beforeLimit, Duration afterLimit,
                      Duration quietAfterStop, AtomicInteger approvalCalls, String source) throws IOException {
        var capture = new PublicCapture();
        var store = new ProbeStore();
        var policy = new MarketStreamProperties(true, true, 2, stock, 15);
        var hub = new MarketStreamHub(policy, store);
        Path journalDir = directory.resolve("journal");
        var journal = new StreamOperationsJournal(true, journalDir.toString(), 256, 1024 * 1024, 1024 * 1024);
        Phase before = null;
        Phase after = null;
        Instant fault = null;
        String failure = null;
        KisStreamConnection.RecoverySnapshot stopped;
        boolean earlyReset = false;
        int arrivalsAtStop;
        int dialsAtStop;
        int arrivals;
        int dials;
        try (var tunnel = new KisProbeTunnel(upstream)) {
            var connection = new KisStreamConnection(kis, policy, hub, rest, JSON,
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5)).build(), tunnel.endpoint(), timing, clock,
                journal, capture::observe);
            try {
                connection.start();
                before = awaitPhase(connection, hub, capture, tunnel, stock, clock, 1, 0, beforeLimit);
                tunnel.resetFirst();
                fault = clock.instant();
                after = awaitPhase(connection, hub, capture, tunnel, stock, clock, 2, before.generation(), afterLimit);
                var observed = connection.recoverySnapshot();
                long firstReadySequence = before.readySequence();
                long recoveredSequence = after.readySequence();
                if (observed.receipts().stream().noneMatch(receipt ->
                    receipt.sequence() > firstReadySequence && receipt.sequence() < recoveredSequence
                        && "RECONNECTING".equals(receipt.state()))) {
                    throw new ProbeFailure("RECONNECT_TRANSITION_NOT_OBSERVED");
                }
                earlyReset = observed.failures() == 0 || observed.receipts().stream().anyMatch(r -> "STABLE".equals(r.state()));
                if (earlyReset) throw new ProbeFailure("EARLY_FAILURE_BUDGET_RESET");
            } catch (ProbeFailure error) {
                failure = error.code;
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                failure = "PROBE_INTERRUPTED";
            } catch (IOException | RuntimeException error) {
                failure = "PROBE_TRANSPORT_OR_SETUP_FAILED";
            } finally {
                connection.stop();
            }
            stopped = connection.recoverySnapshot();
            if (failure == null) {
                long readySequence = after.readySequence();
                if (stopped.receipts().stream().anyMatch(r -> r.sequence() > readySequence
                    && ("RECONNECTING".equals(r.state()) || "FAILED".equals(r.state())))) {
                    failure = "PROBE_RECOVERED_CONNECTION_DROPPED";
                }
            }
            arrivalsAtStop = tunnel.arrivals();
            dialsAtStop = tunnel.upstreamDials();
            try {
                Thread.sleep(quietAfterStop.toMillis());
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                failure = "PROBE_INTERRUPTED";
            }
            arrivals = tunnel.arrivals();
            dials = tunnel.upstreamDials();
            if (failure == null && (!stopped.stopped() || stopped.attempts() != 2 || arrivals != 2 || dials != 2
                || arrivals != arrivalsAtStop || dials != dialsAtStop || approvalCalls.get() != 1)) {
                failure = "PROBE_CONNECTION_BUDGET_OR_STOP_MISMATCH";
            }
        }
        var scans = Files.isDirectory(journalDir)
            ? StreamOperationsJournalInspector.scanDirectory(journalDir, null, ignored -> {}) : List.<StreamOperationsJournalInspector.SessionScan>of();
        boolean cleanEnd = scans.size() == 1 && "CLEAN_END".equals(scans.get(0).status())
            && "CLOSED".equals(stopped.journal().state());
        if (failure == null && !cleanEnd) failure = "PROBE_JOURNAL_INCOMPLETE";
        var frames = capture.frames();
        if (capture.exceeded) failure = "PROBE_PUBLIC_SAMPLE_LIMIT";
        var result = new Result("SAGOPALGO_KIS_RECOVERY_PROBE_V1", source,
            failure == null ? "RECOVERY_OBSERVED" : "INCONCLUSIVE", failure, stock, fault, before, after,
            approvalCalls.get(), arrivals, dials, arrivalsAtStop, dialsAtStop, store.unique(), store.duplicates(),
            frameCount(frames, before), frameCount(frames, after), earlyReset, volumeBoundary(before, after, frames),
            stopped, cleanEnd, false);
        writeEvidence(directory.resolve("public-frames.json"), frames);
        writeEvidence(directory.resolve("receipt.json"), result);
        return result;
    }

    private static int frameCount(List<Observation> frames, Phase phase) {
        return phase == null ? 0 : (int) frames.stream().filter(frame -> frame.generation() == phase.generation()).count();
    }

    private static Phase awaitPhase(KisStreamConnection connection, MarketStreamHub hub, PublicCapture capture,
                                    KisProbeTunnel tunnel, String stock, Clock clock, int attempt, long olderGeneration,
                                    Duration limit) throws ProbeFailure, InterruptedException {
        long deadline = System.nanoTime() + limit.toNanos();
        do {
            var status = connection.recoverySnapshot();
            if (status.terminal() || status.attempts() > attempt || tunnel.arrivals() > attempt
                || (attempt == 1 && status.failures() > 0)) {
                throw new ProbeFailure("PROBE_UNEXPECTED_CONNECTION_STATE");
            }
            if (status.attempts() == attempt && tunnel.upstreamDials() == attempt) {
                for (var ready : status.receipts()) {
                    if (!"DATA_READY".equals(ready.state()) || ready.generation() <= olderGeneration) continue;
                    boolean acked = status.receipts().stream().anyMatch(ack -> "CONNECTED".equals(ack.state())
                        && ack.generation() == ready.generation() && ack.sequence() < ready.sequence());
                    if (!acked) continue;
                    var snapshot = hub.snapshot(stock, clock.instant());
                    if ("LIVE".equals(snapshot.state()) && capture.contains(ready.generation(), snapshot.trade(), snapshot.quote())) {
                        return new Phase(ready.generation(), ready.sequence(), snapshot.trade(), snapshot.quote());
                    }
                }
            }
            Thread.sleep(25);
        } while (System.nanoTime() < deadline);
        throw new ProbeFailure(attempt == 1 ? "PROBE_BASELINE_TIMEOUT" : "PROBE_RECOVERY_TIMEOUT");
    }

    private static VolumeBoundary volumeBoundary(Phase before, Phase after, List<Observation> frames) {
        if (before == null || after == null) return new VolumeBoundary("UNDETERMINED", null, null, null);
        var decoder = new KisStreamDecoder();
        var date = before.trade().marketTime().atZone(SEOUL).toLocalDate();
        var knownIds = new HashSet<String>();
        var lastBefore = before.trade();
        for (var frame : frames) {
            if (frame.generation() != before.generation()) continue;
            for (var trade : decoder.decode(frame.publicFrame(), frame.receivedAt())) {
                if (!isTradeOn(trade, date) || !knownIds.add(trade.eventId())) continue;
                if (new BigInteger(trade.cumulativeVolume()).compareTo(new BigInteger(lastBefore.cumulativeVolume())) > 0) {
                    lastBefore = trade;
                }
            }
        }
        var baseline = new BigInteger(lastBefore.cumulativeVolume());
        for (var frame : frames) {
            if (frame.generation() != after.generation()) continue;
            for (var trade : decoder.decode(frame.publicFrame(), frame.receivedAt())) {
                if (!isTradeOn(trade, date) || knownIds.contains(trade.eventId())) continue;
                var cumulative = new BigInteger(trade.cumulativeVolume());
                var excess = cumulative.subtract(baseline).subtract(new BigInteger(trade.volume()));
                if (cumulative.compareTo(baseline) <= 0 || excess.signum() < 0 || trade.marketTime().isBefore(lastBefore.marketTime())) {
                    return new VolumeBoundary("CUMULATIVE_BOUNDARY_INCONSISTENT", lastBefore.eventId(), trade.eventId(), null);
                }
                return new VolumeBoundary(excess.signum() == 0 ? "NO_EXCESS_IN_OBSERVED_BOUNDARY"
                    : "CUMULATIVE_EXCESS_IN_OBSERVED_BOUNDARY", lastBefore.eventId(), trade.eventId(), excess.toString());
            }
        }
        return new VolumeBoundary("UNDETERMINED", lastBefore.eventId(), null, null);
    }

    private static boolean isTradeOn(MarketStreamEvent event, LocalDate date) {
        return "TRADE".equals(event.type()) && date.equals(event.marketTime().atZone(SEOUL).toLocalDate());
    }

    private static void writeEvidence(Path output, Object evidence) throws IOException {
        byte[] bytes = JSON.writeValueAsBytes(evidence);
        Files.write(output, bytes, java.nio.file.StandardOpenOption.CREATE_NEW);
    }

    private static final class PublicCapture {
        private final List<Observation> frames = new ArrayList<>();
        private final Map<Long,Set<String>> eventIds = new HashMap<>();
        private int bytes;
        private int count;
        private boolean exceeded;

        synchronized void observe(long generation, String frame, List<MarketStreamEvent> events) {
            int size = frame.getBytes(StandardCharsets.UTF_8).length;
            if (bytes + size > MAX_FRAME_BYTES || count + events.size() > MAX_EVENTS) {
                exceeded = true;
                throw new IllegalStateException("PROBE_PUBLIC_SAMPLE_LIMIT");
            }
            bytes += size;
            count += events.size();
            var ids = events.stream().map(MarketStreamEvent::eventId).toList();
            eventIds.computeIfAbsent(generation, ignored -> new HashSet<>()).addAll(ids);
            frames.add(new Observation(generation, KisStreamDecoder.hash(frame), frame, events.get(0).receivedAt(), ids));
        }

        synchronized boolean contains(long generation, MarketStreamEvent trade, MarketStreamEvent quote) {
            var observed = eventIds.getOrDefault(generation, Set.of());
            return observed.contains(trade.eventId()) && observed.contains(quote.eventId());
        }

        synchronized List<Observation> frames() { return List.copyOf(frames); }
    }

    private static final class ProbeStore extends MarketStreamStore {
        private final Map<String,MarketStreamEvent> events = new HashMap<>();
        private int duplicates;
        ProbeStore() { super(null, JSON); }
        @Override public void verify() {}
        @Override public List<StreamMinuteBar> minutes(String stock, Instant from) { return List.of(); }
        @Override public synchronized boolean appendCommitted(MarketStreamEvent event, Runnable afterCommit) {
            var previous = events.get(event.eventId());
            if (previous != null) {
                if (!previous.marketTime().equals(event.marketTime()) || !Objects.equals(previous.price(), event.price())
                    || !Objects.equals(previous.volume(), event.volume())) throw new IllegalStateException("PROBE_EVENT_CONFLICT");
                duplicates++;
                return false;
            }
            if (events.size() >= MAX_EVENTS) throw new IllegalStateException("PROBE_EVENT_LIMIT");
            events.put(event.eventId(), event);
            afterCommit.run();
            return true;
        }
        synchronized int unique() { return events.size(); }
        synchronized int duplicates() { return duplicates; }
    }

    private static final class ProbeFailure extends Exception {
        final String code;
        ProbeFailure(String code) { this.code = code; }
    }

    static RestClient boundedApprovalClient(AtomicInteger calls) {
        var factory = new JdkClientHttpRequestFactory(HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(5)).followRedirects(HttpClient.Redirect.NEVER).build());
        factory.setReadTimeout(Duration.ofSeconds(5));
        return RestClient.builder().requestFactory(factory).requestInterceptor((request, body, execution) -> {
            if (request.getMethod() != HttpMethod.POST || !URI.create(KIS_ORIGIN + "/oauth2/Approval").equals(request.getURI())
                || !calls.compareAndSet(0, 1)) {
                throw new IOException("PROBE_APPROVAL_BUDGET");
            }
            return execution.execute(request, body);
        }).build();
    }

    private static KisMarketProperties credentials(Path envFile) throws IOException {
        var values = new HashMap<String,String>();
        if (Files.isRegularFile(envFile, LinkOption.NOFOLLOW_LINKS)) {
            try (var lines = Files.lines(envFile)) {
                lines.forEach(line -> {
                    int separator = line.indexOf('=');
                    if (separator <= 0) return;
                    String name = line.substring(0, separator).trim();
                    if (!Set.of(KEY, SECRET, STREAM_ENABLED).contains(name)) return;
                    String value = line.substring(separator + 1).trim();
                    if (value.length() >= 2 && ((value.startsWith("\"") && value.endsWith("\""))
                        || (value.startsWith("'") && value.endsWith("'")))) value = value.substring(1, value.length() - 1);
                    if (values.putIfAbsent(name, value) != null) throw new IllegalArgumentException("PROBE_CREDENTIAL_FILE_AMBIGUOUS");
                });
            }
        }
        if (collectorEnabled(values.get(STREAM_ENABLED)) || collectorEnabled(System.getenv(STREAM_ENABLED))) {
            throw new IllegalArgumentException("PROBE_SHARED_COLLECTOR_ENABLED");
        }
        String key = System.getenv().getOrDefault(KEY, values.getOrDefault(KEY, ""));
        String secret = System.getenv().getOrDefault(SECRET, values.getOrDefault(SECRET, ""));
        if (!key.matches("[A-Za-z0-9+/=_-]{1,512}") || !secret.matches("[A-Za-z0-9+/=_-]{1,512}")) {
            throw new IllegalArgumentException("PROBE_KIS_CREDENTIALS_REQUIRED");
        }
        var props = new KisMarketProperties();
        props.setEnabled(true);
        props.setBaseUrl(KIS_ORIGIN);
        props.setAppKey(key);
        props.setAppSecret(secret);
        return props;
    }

    private static boolean collectorEnabled(String value) {
        return value != null && !value.isBlank() && !"false".equalsIgnoreCase(value.trim());
    }

    static int launch(String[] args, Clock clock) {
        var watchdog = Executors.newSingleThreadScheduledExecutor(task -> {
            var thread = new Thread(task, "kis-probe-deadline");
            thread.setDaemon(true);
            return thread;
        });
        try {
            var options = StreamOperationsJournalInspector.parseOptions(args, Set.of("--market-date", "--stock-code",
                "--confirmed-regular-session", "--confirmed-two-exclusive-subscriptions", "--confirmed-personal-use"));
            if (!"true".equals(options.get("--confirmed-regular-session"))
                || !"true".equals(options.get("--confirmed-two-exclusive-subscriptions"))
                || !"true".equals(options.get("--confirmed-personal-use"))) {
                System.err.println("KIS_RECOVERY_PROBE_CONFIRMATIONS_REQUIRED");
                return 2;
            }
            String stock = options.getOrDefault("--stock-code", "");
            if (!stock.matches("[0-9]{6}")) throw new IllegalArgumentException("PROBE_SYMBOL_INVALID");
            LocalDate date = LocalDate.parse(options.get("--market-date"));
            try {
                requireWindow(date, clock);
            } catch (IllegalArgumentException outsideWindow) {
                System.err.println("KIS_RECOVERY_PROBE_OUTSIDE_KRX_WINDOW");
                return 2;
            }
            watchdog.schedule(() -> Runtime.getRuntime().halt(124), HARD_LIMIT_SECONDS, TimeUnit.SECONDS);
            var kis = credentials(Path.of("..", "..", ".env"));
            Path root = Path.of("build-codex-kis-recovery");
            Files.createDirectories(root);
            Path out = Files.createTempDirectory(root, stock + "-");
            System.out.println("KIS_RECOVERY_PROBE_OUTPUT " + out);
            requireWindow(date, clock);
            var approvals = new AtomicInteger();
            var result = run(out, stock, KisStreamConnection.ENDPOINT, kis, boundedApprovalClient(approvals), clock,
                KisStreamConnection.Timing.production(), Duration.ofSeconds(32), Duration.ofSeconds(38),
                Duration.ofSeconds(6), approvals, "KIS_INTRADAY_CAPTURE");
            System.out.println(result.status());
            return "RECOVERY_OBSERVED".equals(result.status()) ? 0 : 1;
        } catch (Exception error) {
            System.err.println("KIS_RECOVERY_PROBE_FAILED");
            return 2;
        } finally {
            watchdog.shutdownNow();
        }
    }

    public static void main(String[] args) { System.exit(launch(args, Clock.systemUTC())); }
}
