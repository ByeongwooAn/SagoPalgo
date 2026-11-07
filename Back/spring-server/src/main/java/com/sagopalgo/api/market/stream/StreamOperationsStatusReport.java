package com.sagopalgo.api.market.stream;

import com.sagopalgo.api.market.stream.StreamOperationsJournal.Counters;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Entry;
import com.sagopalgo.api.market.stream.StreamOperationsJournalInspector.SessionScan;
import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.TreeMap;
import java.util.UUID;

/** Summarizes only the verified prefix of each operations journal session. */
public final class StreamOperationsStatusReport {
    static final int RECOVERY_WINDOW_LIMIT = 16;

    enum Source { UNSPECIFIED, SYNTHETIC, CAPTURE }

    record Report(String schemaVersion, Source declaredSource, boolean sourceProvenanceVerified,
                  String crossSessionOrder, String writerActivity, boolean usableForTrading,
                  EvidenceBounds evidenceBounds, List<SessionSummary> sessions) {}

    record EvidenceBounds(String databaseRowComparison, String databaseRowMatching,
                          String counterSemantics, String providerEventContinuity, Long missingProviderEvents) {}

    record SessionSummary(UUID sessionId, UUID clockDomain, boolean utcSynchronized, String integrityStatus,
                          long verifiedEntries, String fileSha256, String lastVerifiedHash,
                          Boundary firstVerified, Boundary lastVerified, Map<String,Long> lifecycleCounts,
                          Map<String,Long> diagnosticCounts, long counterCheckpoints, Counters latestCounters,
                          Delays delays, Recovery recovery, Tail tail) {}

    record Boundary(long index, long generation, long elapsedNanos, String observedAt, String state) {}
    record DurationStats(long samples, Long minimumNanos, Long maximumNanos) {}
    record Delays(DurationStats attemptToAck, DurationStats ackToDataReady,
                  long unpairedAcks, long unpairedDataReady) {}
    record Recovery(long started, long recovered, long endedWithoutDataReady, DurationStats timeToDataReady,
                    long olderClosedWindowsOmitted, List<RecoveryWindow> recentClosedWindows,
                    RecoveryWindow unresolvedWindow) {}
    record RecoveryWindow(Boundary from, Boundary to, String outcome, Long elapsedNanos) {}
    record Tail(String assessment, Long inFlightStorage, Long unobservedOperations) {}

    static Report build(Path directory, UUID selected, Source source) throws IOException {
        Objects.requireNonNull(source);
        var metrics = new HashMap<UUID,SessionMetrics>();
        var scanned = StreamOperationsJournalInspector.scanDirectory(directory, selected, record ->
            metrics.computeIfAbsent(record.entry().sessionId(), ignored -> new SessionMetrics()).observe(record));
        var sessions = scanned.stream()
            .map(session -> metrics.computeIfAbsent(session.sessionId(), ignored -> new SessionMetrics()).summarize(session))
            .toList();
        return new Report("SAGOPALGO_STREAM_OPERATIONS_STATUS_V1", source, false, "UNCONFIRMED",
            "NOT_DETERMINED", false,
            new EvidenceBounds("NOT_PERFORMED", "EVENT_IDENTITIES_UNAVAILABLE",
                "METHOD_OUTCOME_SNAPSHOTS", "NOT_DETERMINED_FROM_JOURNAL", null), sessions);
    }

    private static final class SessionMetrics {
        private final Map<String,Long> lifecycle = new TreeMap<>();
        private final Map<String,Long> diagnostics = new TreeMap<>();
        private final Samples attemptToAck = new Samples();
        private final Samples ackToReady = new Samples();
        private final Samples recoveryTime = new Samples();
        private final ArrayDeque<RecoveryWindow> recentClosed = new ArrayDeque<>();
        private Boundary first;
        private Boundary last;
        private Boundary attempt;
        private Boundary ack;
        private boolean dataReady;
        private Boundary recoveryStart;
        private long checkpoints;
        private long unpairedAcks;
        private long unpairedDataReady;
        private long recoveryStarts;
        private long endedWithoutDataReady;
        private long omittedWindows;

        void observe(Entry record) {
            var body = record.entry();
            var operation = body.operation();
            last = new Boundary(body.index(), operation.generation(), operation.elapsedNanos(),
                operation.observedAt(), operation.state());
            switch (body.kind()) {
                case START -> first = last;
                case COUNTERS -> checkpoints++;
                case END -> terminate(last);
                case LIFECYCLE -> {
                    lifecycle.merge(operation.state(), 1L, Long::sum);
                    if (operation.code() != null) diagnostics.merge(operation.code(), 1L, Long::sum);
                    observeLifecycle(last);
                }
            }
        }

        private void observeLifecycle(Boundary event) {
            switch (event.state()) {
                case "CONNECTING" -> {
                    attempt = event;
                    ack = null;
                    dataReady = false;
                }
                case "CONNECTED" -> acknowledge(event);
                case "DATA_READY" -> dataReady(event);
                case "RECONNECTING" -> {
                    attempt = null;
                    if (recoveryStart == null) {
                        recoveryStart = event;
                        recoveryStarts++;
                    }
                }
                case "FAILED", "DISABLED" -> terminate(event);
                default -> { /* SUBSCRIBING and STABLE contribute to lifecycle counts. */ }
            }
        }

        private void acknowledge(Boundary event) {
            if (!matchesAttempt(event) || ack != null) {
                unpairedAcks++;
                return;
            }
            ack = event;
            attemptToAck.observe(event.elapsedNanos() - attempt.elapsedNanos());
        }

        private void dataReady(Boundary event) {
            if (!matchesAttempt(event) || ack == null || dataReady) {
                unpairedDataReady++;
                return;
            }
            dataReady = true;
            ackToReady.observe(event.elapsedNanos() - ack.elapsedNanos());
            if (recoveryStart != null && attempt.generation() > recoveryStart.generation()) {
                recoveryTime.observe(event.elapsedNanos() - recoveryStart.elapsedNanos());
                closeRecovery(event, "DATA_READY_RECORDED");
            }
        }

        private boolean matchesAttempt(Boundary event) {
            return attempt != null && attempt.generation() == event.generation();
        }

        private void terminate(Boundary event) {
            attempt = null;
            if (recoveryStart != null) {
                endedWithoutDataReady++;
                closeRecovery(event, "ENDED_BEFORE_DATA_READY");
            }
        }

        private void closeRecovery(Boundary end, String outcome) {
            if (recentClosed.size() == RECOVERY_WINDOW_LIMIT) {
                recentClosed.removeFirst();
                omittedWindows++;
            }
            recentClosed.addLast(new RecoveryWindow(recoveryStart, end, outcome,
                end.elapsedNanos() - recoveryStart.elapsedNanos()));
            recoveryStart = null;
        }

        SessionSummary summarize(SessionScan scan) {
            Counters counters = scan.lastOperation() == null ? null : scan.lastOperation().counters();
            Long inFlight = counters == null ? null : counters.inFlightStorage();
            var unresolved = recoveryStart == null ? null :
                new RecoveryWindow(recoveryStart, null, "VERIFIED_PREFIX_ENDED", null);
            var recovery = new Recovery(recoveryStarts, recoveryTime.count, endedWithoutDataReady, recoveryTime.stats(),
                omittedWindows, List.copyOf(recentClosed), unresolved);
            return new SessionSummary(scan.sessionId(), scan.clockDomain(), false, scan.status(), scan.verifiedEntries(),
                scan.fileSha256(), scan.lastVerifiedHash(), first, last, lifecycle, diagnostics, checkpoints, counters,
                new Delays(attemptToAck.stats(), ackToReady.stats(), unpairedAcks, unpairedDataReady),
                recovery, new Tail(tailAssessment(scan.status(), inFlight), inFlight, null));
        }

        private static String tailAssessment(String status, Long inFlight) {
            return switch (status) {
                case "CLEAN_END" -> inFlight != null && inFlight > 0 ? "END_WITH_IN_FLIGHT_STORAGE" : "END_MARKER_VERIFIED";
                case "NO_END_MARKER" -> "END_NOT_VERIFIED";
                case "PARTIAL_TAIL" -> "PARTIAL_LINE";
                case "CORRUPT" -> "INVALID_LINE";
                case "EMPTY" -> "NO_RECORDS";
                default -> throw new IllegalArgumentException("JOURNAL_STATUS_INVALID");
            };
        }
    }

    private static final class Samples {
        private long count;
        private long min = Long.MAX_VALUE;
        private long max;

        void observe(long durationNanos) {
            count++;
            min = Math.min(min, durationNanos);
            max = Math.max(max, durationNanos);
        }

        DurationStats stats() {
            return new DurationStats(count, count == 0 ? null : min, count == 0 ? null : max);
        }
    }

    static int run(String[] args) {
        try {
            var options = StreamOperationsJournalInspector.parseOptions(args,
                Set.of("--directory", "--output", "--session", "--source"));
            Path output = Path.of(options.get("--output"));
            if (!output.getFileName().toString().endsWith(".json")) throw new IllegalArgumentException();
            UUID selected = options.containsKey("--session") ? UUID.fromString(options.get("--session")) : null;
            var source = Source.valueOf(options.getOrDefault("--source", "UNSPECIFIED"));
            var report = build(Path.of(options.get("--directory")), selected, source);
            StreamOperationsJournalInspector.writeNewReport(output, report);
            return 0;
        } catch (Exception error) {
            System.err.println("{\"status\":\"FAILED\",\"code\":\"JOURNAL_STATUS_REPORT_FAILED\"}");
            return 2;
        }
    }

    public static void main(String[] args) {
        System.exit(run(args));
    }
}
