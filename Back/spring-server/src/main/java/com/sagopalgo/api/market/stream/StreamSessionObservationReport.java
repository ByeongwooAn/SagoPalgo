package com.sagopalgo.api.market.stream;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Entry;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Kind;
import com.sagopalgo.api.market.stream.StreamOperationsStatusReport.Source;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

/** Observes verified journal records against a declared market calendar, without connecting to a provider. */
public final class StreamSessionObservationReport {
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final int BUCKET_MINUTES = 15;
    private static final int MAX_DAYS = 31;
    private static final int MAX_PLAN_BYTES = 32768;
    private static final String PLAN_VERSION = "SAGOPALGO_STREAM_SESSION_PLAN_V1";

    enum MarketDay { OPEN, CLOSED, UNKNOWN }
    enum Phase { BEFORE_OPEN, OPENING, REGULAR, CLOSING, AFTER_CLOSE }
    record DayPlan(String date, MarketDay marketDay, String opensAt, String closesAt, String scheduleEvidence) {}
    record Plan(String schemaVersion, Source declaredSource, String stockCode, int approvedSubscriptions, List<DayPlan> days) {}
    record Bucket(String from, String to, long verifiedRecords, String assessment) {}
    record DayObservation(DayPlan schedule, List<UUID> contributingSessions, long verifiedRecords,
                          Map<Phase,Long> phaseRecords, List<Bucket> sessionBuckets, long connectionAttempts,
                          long dataReadyRecords, long reconnectRecords, long failureRecords, String assessment) {}
    record SessionEvidence(UUID sessionId, String integrityStatus, long verifiedRecords, String fileSha256,
                           String timestampAssessment) {}
    record Report(String schemaVersion, String timezone, Source declaredSource, String declaredStockCode,
                  int declaredSubscriptionLimit, boolean declaredScopeVerified, String timestampBasis,
                  String marketContinuity, boolean usableForTrading, long outOfPlanRecords,
                  long excludedClockReversalRecords, List<DayObservation> days, List<SessionEvidence> sessions) {}

    private record DayWindow(DayPlan plan, LocalTime opens, LocalTime closes, long minutes) {
        int buckets() { return (int) ((minutes + BUCKET_MINUTES - 1) / BUCKET_MINUTES); }
        Phase phase(LocalTime time) {
            if (time.isBefore(opens)) return Phase.BEFORE_OPEN;
            if (!time.isBefore(closes)) return Phase.AFTER_CLOSE;
            long edgeSeconds = Math.min(300, minutes * 30);
            if (time.isBefore(opens.plusSeconds(edgeSeconds))) return Phase.OPENING;
            if (!time.isBefore(closes.minusSeconds(edgeSeconds))) return Phase.CLOSING;
            return Phase.REGULAR;
        }
    }

    static Report build(Path directory, Plan plan) throws IOException {
        var windows = validate(plan);
        var timelines = new HashMap<UUID,Timeline>();
        var scans = StreamOperationsJournalInspector.scanDirectory(directory, null, entry ->
            timelines.computeIfAbsent(entry.entry().sessionId(), ignored -> new Timeline()).observe(entry, windows));
        var totals = new LinkedHashMap<LocalDate,DayCounts>();
        windows.forEach((date, window) -> totals.put(date, new DayCounts(window)));
        var evidence = new ArrayList<SessionEvidence>();
        long outOfPlan = 0;
        long reversed = 0;
        for (var scan : scans) {
            var timeline = timelines.get(scan.sessionId());
            String timestampAssessment = "NO_VERIFIED_RECORDS";
            if (timeline != null && timeline.reversed) {
                reversed += scan.verifiedEntries();
                timestampAssessment = "EXCLUDED_WALL_CLOCK_REVERSAL";
            } else if (timeline != null) {
                outOfPlan += timeline.outOfPlan;
                timeline.days.forEach((date, counts) -> totals.get(date).add(scan.sessionId(), counts));
                timestampAssessment = "LOCAL_ORDER_NONDECREASING";
            }
            evidence.add(new SessionEvidence(scan.sessionId(), scan.status(), scan.verifiedEntries(), scan.fileSha256(),
                timestampAssessment));
        }
        return new Report("SAGOPALGO_STREAM_SESSION_OBSERVATION_V1", SEOUL.getId(), plan.declaredSource(),
            plan.stockCode(), plan.approvedSubscriptions(), false, "UNSYNCHRONIZED_LOCAL_WALL_CLOCK",
            "UNDETERMINED_FROM_JOURNAL", false, outOfPlan, reversed,
            totals.values().stream().map(DayCounts::report).toList(), List.copyOf(evidence));
    }

    private static Map<LocalDate,DayWindow> validate(Plan plan) {
        if (!PLAN_VERSION.equals(plan.schemaVersion()) || plan.declaredSource() == null
            || plan.stockCode() == null || !plan.stockCode().matches("[0-9]{6}") || plan.approvedSubscriptions() != 2
            || plan.days() == null || plan.days().isEmpty() || plan.days().size() > MAX_DAYS) {
            throw new IllegalArgumentException("SESSION_PLAN_INVALID");
        }
        var result = new LinkedHashMap<LocalDate,DayWindow>();
        LocalDate previous = null;
        for (var day : plan.days()) {
            LocalDate date = LocalDate.parse(day.date());
            if (previous != null && !date.equals(previous.plusDays(1)) || day.marketDay() == null) {
                throw new IllegalArgumentException("SESSION_PLAN_DATE_INVALID");
            }
            String reference = day.scheduleEvidence();
            if (reference != null && !reference.matches("[A-Za-z0-9._-]{1,100}")
                || day.marketDay() != MarketDay.UNKNOWN && reference == null) {
                throw new IllegalArgumentException("SESSION_PLAN_EVIDENCE_REQUIRED");
            }
            if (day.marketDay() == MarketDay.OPEN) {
                LocalTime open = parseTime(day.opensAt());
                LocalTime close = parseTime(day.closesAt());
                if (!close.isAfter(open)) throw new IllegalArgumentException("SESSION_PLAN_TIME_INVALID");
                result.put(date, new DayWindow(day, open, close, Duration.between(open, close).toMinutes()));
            } else {
                if (day.opensAt() != null || day.closesAt() != null) {
                    throw new IllegalArgumentException("SESSION_PLAN_TIME_INVALID");
                }
                result.put(date, new DayWindow(day, null, null, 0));
            }
            previous = date;
        }
        return result;
    }

    private static LocalTime parseTime(String value) {
        if (value == null || !value.matches("[0-9]{2}:[0-9]{2}")) throw new IllegalArgumentException("SESSION_PLAN_TIME_INVALID");
        return LocalTime.parse(value);
    }

    private static final class Timeline {
        final Map<LocalDate,DayCounts> days = new HashMap<>();
        Instant previous;
        boolean reversed;
        long outOfPlan;

        void observe(Entry entry, Map<LocalDate,DayWindow> windows) {
            if (reversed) return;
            var observed = Instant.parse(entry.entry().operation().observedAt());
            if (previous != null && observed.isBefore(previous)) {
                reversed = true;
                days.clear();
                return;
            }
            previous = observed;
            var local = observed.atZone(SEOUL);
            var date = local.toLocalDate();
            var window = windows.get(date);
            if (window == null) {
                outOfPlan++;
            } else {
                days.computeIfAbsent(date, ignored -> new DayCounts(window)).observe(local.toLocalTime(), entry);
            }
        }
    }

    private static final class DayCounts {
        final DayWindow window;
        final long[] buckets;
        final long[] phases = new long[Phase.values().length];
        final Set<UUID> sessionIds = new LinkedHashSet<>();
        long records;
        long attempts;
        long ready;
        long reconnects;
        long failures;
        boolean connectionActivity;

        DayCounts(DayWindow window) {
            this.window = window;
            buckets = new long[window.buckets()];
        }

        void observe(LocalTime time, Entry entry) {
            records++;
            if (window.opens() != null) {
                var phase = window.phase(time);
                phases[phase.ordinal()]++;
                if (phase != Phase.BEFORE_OPEN && phase != Phase.AFTER_CLOSE) {
                    int bucket = (int) (Duration.between(window.opens(), time).toMinutes() / BUCKET_MINUTES);
                    buckets[bucket]++;
                }
            }
            if (entry.entry().kind() != Kind.LIFECYCLE) return;
            switch (entry.entry().operation().state()) {
                case "CONNECTING" -> { attempts++; connectionActivity = true; }
                case "DATA_READY" -> { ready++; connectionActivity = true; }
                case "RECONNECTING" -> { reconnects++; connectionActivity = true; }
                case "SUBSCRIBING", "CONNECTED", "STABLE" -> connectionActivity = true;
                case "FAILED" -> failures++;
                default -> {}
            }
        }

        void add(UUID id, DayCounts other) {
            sessionIds.add(id);
            records += other.records;
            attempts += other.attempts;
            ready += other.ready;
            reconnects += other.reconnects;
            failures += other.failures;
            connectionActivity |= other.connectionActivity;
            for (int i = 0; i < buckets.length; i++) buckets[i] += other.buckets[i];
            for (int i = 0; i < phases.length; i++) phases[i] += other.phases[i];
        }

        DayObservation report() {
            var phaseRecords = new EnumMap<Phase,Long>(Phase.class);
            var intervals = new ArrayList<Bucket>();
            if (window.opens() != null) {
                for (var phase : Phase.values()) phaseRecords.put(phase, phases[phase.ordinal()]);
                for (int i = 0; i < buckets.length; i++) {
                    var from = window.opens().plusMinutes((long) i * BUCKET_MINUTES);
                    var to = window.opens().plusMinutes(Math.min(window.minutes(), (long) (i + 1) * BUCKET_MINUTES));
                    intervals.add(new Bucket(from.toString(), to.toString(), buckets[i],
                        buckets[i] == 0 ? "NO_VERIFIED_RECORDS" : "VERIFIED_RECORDS_PRESENT"));
                }
            }
            String assessment = switch (window.plan().marketDay()) {
                case UNKNOWN -> "SCHEDULE_UNCONFIRMED";
                case CLOSED -> connectionActivity ? "CLOSED_DAY_CONNECTION_ACTIVITY_OBSERVED"
                    : records == 0 ? "CLOSED_DAY_UNOBSERVED" : "CLOSED_DAY_NO_CONNECTION_RECORD";
                case OPEN -> assessOpen();
            };
            return new DayObservation(window.plan(), List.copyOf(sessionIds), records, phaseRecords,
                List.copyOf(intervals), attempts, ready, reconnects, failures, assessment);
        }

        private String assessOpen() {
            boolean any = false;
            boolean gap = false;
            for (long count : buckets) {
                any |= count > 0;
                gap |= count == 0;
            }
            if (!any) return "OPEN_SESSION_UNOBSERVED";
            return gap ? "OPEN_SESSION_WITH_UNOBSERVED_BUCKETS" : "EVERY_BUCKET_HAS_RECORDS";
        }
    }

    static int run(String[] args) {
        try {
            var options = StreamOperationsJournalInspector.parseOptions(args, Set.of("--directory", "--plan", "--output"));
            byte[] data;
            try (var stream = Files.newInputStream(Path.of(options.get("--plan")), LinkOption.NOFOLLOW_LINKS)) {
                data = stream.readNBytes(MAX_PLAN_BYTES + 1);
            }
            if (data.length > MAX_PLAN_BYTES) throw new IllegalArgumentException("SESSION_PLAN_LIMIT");
            Plan plan = StreamOperationsJournal.JSON.readerFor(Plan.class)
                .with(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS).readValue(data);
            Path output = Path.of(options.get("--output"));
            if (!output.getFileName().toString().endsWith(".json")) throw new IllegalArgumentException("SESSION_REPORT_OUTPUT_INVALID");
            StreamOperationsJournalInspector.writeNewReport(output, build(Path.of(options.get("--directory")), plan));
            return 0;
        } catch (Exception error) {
            System.err.println("{\"status\":\"FAILED\",\"code\":\"STREAM_SESSION_OBSERVATION_FAILED\"}");
            return 2;
        }
    }

    public static void main(String[] args) { System.exit(run(args)); }
}
