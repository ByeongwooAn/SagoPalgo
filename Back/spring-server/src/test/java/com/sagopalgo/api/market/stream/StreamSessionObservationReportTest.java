package com.sagopalgo.api.market.stream;

import static com.sagopalgo.api.market.stream.StreamSessionObservationReport.MarketDay.*;
import static org.assertj.core.api.Assertions.*;

import com.sagopalgo.api.market.stream.StreamOperationsJournal.Counters;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Kind;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Operation;
import com.sagopalgo.api.market.stream.StreamOperationsStatusReport.Source;
import com.sagopalgo.api.market.stream.StreamSessionObservationReport.DayPlan;
import com.sagopalgo.api.market.stream.StreamSessionObservationReport.Phase;
import com.sagopalgo.api.market.stream.StreamSessionObservationReport.Plan;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class StreamSessionObservationReportTest {
    @TempDir Path root;

    @Test void observesOpenAndCloseWithExactBoundsAndKeepsQuietIntervalsUnobserved() throws Exception {
        UUID session = journal("2026-11-06T23:59:59+09:00", "2026-11-09T15:30:01+09:00", List.of(
            new RecordAt("2026-11-09T08:59:59+09:00", "CONNECTING"),
            new RecordAt("2026-11-09T09:00:00+09:00", "CONNECTED"),
            new RecordAt("2026-11-09T09:04:59+09:00", "DATA_READY"),
            new RecordAt("2026-11-09T09:05:00+09:00", "COUNTERS"),
            new RecordAt("2026-11-09T14:00:00+09:00", "RECONNECTING"),
            new RecordAt("2026-11-09T15:25:00+09:00", "DATA_READY"),
            new RecordAt("2026-11-09T15:30:00+09:00", "DISABLED")));
        var report = StreamSessionObservationReport.build(root, plan(open("2026-11-09")));
        var day = report.days().get(0);
        assertThat(report.outOfPlanRecords()).isEqualTo(1);
        assertThat(day.contributingSessions()).containsExactly(session);
        assertThat(day.phaseRecords()).containsEntry(Phase.BEFORE_OPEN, 1L).containsEntry(Phase.OPENING, 2L)
            .containsEntry(Phase.REGULAR, 2L).containsEntry(Phase.CLOSING, 1L).containsEntry(Phase.AFTER_CLOSE, 2L);
        assertThat(day.sessionBuckets()).hasSize(26);
        assertThat(day.sessionBuckets().get(0).verifiedRecords()).isEqualTo(3);
        assertThat(day.sessionBuckets().get(1).assessment()).isEqualTo("NO_VERIFIED_RECORDS");
        assertThat(day.sessionBuckets().get(25).from()).isEqualTo("15:15");
        assertThat(day.sessionBuckets().get(25).to()).isEqualTo("15:30");
        assertThat(day.connectionAttempts()).isEqualTo(1);
        assertThat(day.dataReadyRecords()).isEqualTo(2);
        assertThat(day.reconnectRecords()).isEqualTo(1);
        assertThat(day.assessment()).isEqualTo("OPEN_SESSION_WITH_UNOBSERVED_BUCKETS");
        assertThat(report.marketContinuity()).isEqualTo("UNDETERMINED_FROM_JOURNAL");
    }

    @Test void allSessionBucketsCanHaveRecordsWhileMarketContinuityRemainsUndetermined() throws Exception {
        var first = Instant.parse("2026-11-09T00:00:00Z");
        var records = new ArrayList<RecordAt>();
        for (int i = 0; i < 26; i++) records.add(new RecordAt(first.plusSeconds(i * 900L).toString(), "COUNTERS"));
        journal(first.toString(), "2026-11-09T06:30:00Z", records);
        var report = StreamSessionObservationReport.build(root, plan(open("2026-11-09")));
        assertThat(report.days().get(0).assessment()).isEqualTo("EVERY_BUCKET_HAS_RECORDS");
        assertThat(report.days().get(0).sessionBuckets()).allMatch(bucket -> bucket.verifiedRecords() > 0);
        assertThat(report.marketContinuity()).isEqualTo("UNDETERMINED_FROM_JOURNAL");
        assertThat(report.declaredScopeVerified()).isFalse();
        assertThat(report.usableForTrading()).isFalse();
    }

    @Test void closedDaysDistinguishObservedConnectionFromNoRecordsAndUnknownSchedule() throws Exception {
        journal("2026-11-07T08:59:00+09:00", "2026-11-07T09:00:01+09:00",
            List.of(new RecordAt("2026-11-07T09:00:00+09:00", "CONNECTED")));
        journal("2026-11-08T09:00:00+09:00", "2026-11-08T09:01:00+09:00", List.of());
        var report = StreamSessionObservationReport.build(root, plan(
            closed("2026-11-07"), closed("2026-11-08"), closed("2026-11-09"), open("2026-11-10"),
            new DayPlan("2026-11-11", UNKNOWN, null, null, null)));
        assertThat(report.days()).extracting(StreamSessionObservationReport.DayObservation::assessment).containsExactly(
            "CLOSED_DAY_CONNECTION_ACTIVITY_OBSERVED", "CLOSED_DAY_NO_CONNECTION_RECORD", "CLOSED_DAY_UNOBSERVED",
            "OPEN_SESSION_UNOBSERVED", "SCHEDULE_UNCONFIRMED");
        assertThat(report.days().get(0).sessionBuckets()).isEmpty();
        assertThat(report.days().get(0).connectionAttempts()).isZero();
        assertThat(report.days().get(3).sessionBuckets()).hasSize(26);
    }

    @Test void wallClockReversalExcludesTheWholeTimelineAndRetainsIntegrityEvidence() throws Exception {
        UUID id = journal("2026-11-09T09:01:00+09:00", "2026-11-09T09:04:00+09:00", List.of(
            new RecordAt("2026-11-09T09:02:00+09:00", "CONNECTING"),
            new RecordAt("2026-11-09T09:01:59+09:00", "CONNECTED")));
        var report = StreamSessionObservationReport.build(root, plan(open("2026-11-09")));
        assertThat(report.excludedClockReversalRecords()).isEqualTo(4);
        assertThat(report.days().get(0).verifiedRecords()).isZero();
        assertThat(report.sessions()).singleElement().satisfies(session -> {
            assertThat(session.sessionId()).isEqualTo(id);
            assertThat(session.integrityStatus()).isEqualTo("CLEAN_END");
            assertThat(session.timestampAssessment()).isEqualTo("EXCLUDED_WALL_CLOCK_REVERSAL");
        });
    }

    @Test void usesOnlyVerifiedPrefixFromCorruptFileAndDoesNotRewriteIt() throws Exception {
        UUID id = journal("2026-11-09T09:01:00+09:00", "2026-11-09T09:02:00+09:00", List.of());
        Path file = root.resolve("session-" + id + ".jsonl");
        Files.writeString(file, "{}\n", StandardOpenOption.APPEND);
        byte[] before = Files.readAllBytes(file);
        var report = StreamSessionObservationReport.build(root, plan(open("2026-11-09")));
        assertThat(report.sessions().get(0).integrityStatus()).isEqualTo("CORRUPT");
        assertThat(report.days().get(0).verifiedRecords()).isEqualTo(2);
        assertThat(Files.readAllBytes(file)).isEqualTo(before);
    }

    @Test void validatesConsecutiveDatesExplicitScheduleAndFixedBudget() {
        assertThatThrownBy(() -> StreamSessionObservationReport.build(root, plan(open("2026-11-06"), open("2026-11-09"))))
            .hasMessage("SESSION_PLAN_DATE_INVALID");
        assertThatThrownBy(() -> StreamSessionObservationReport.build(root,
            plan(new DayPlan("2026-11-06", CLOSED, null, null, null)))).hasMessage("SESSION_PLAN_EVIDENCE_REQUIRED");
        assertThatThrownBy(() -> StreamSessionObservationReport.build(root,
            plan(new DayPlan("2026-11-06", OPEN, "10:00", "09:00", "TEST")))).hasMessage("SESSION_PLAN_TIME_INVALID");
        var valid = plan(open("2026-11-06"));
        assertThatThrownBy(() -> StreamSessionObservationReport.build(root,
            new Plan(valid.schemaVersion(), valid.declaredSource(), valid.stockCode(), 3, valid.days())))
            .hasMessage("SESSION_PLAN_INVALID");
    }

    @Test void commandWritesOnlyANewReport() throws Exception {
        Path planPath = root.resolve("plan.json");
        Path output = root.resolve("result.json");
        Files.write(planPath, StreamOperationsJournal.JSON.writeValueAsBytes(plan(open("2026-11-09"))));
        var args = new String[]{"--directory", root.toString(), "--plan", planPath.toString(), "--output", output.toString()};
        assertThat(StreamSessionObservationReport.run(args)).isZero();
        byte[] before = Files.readAllBytes(output);
        var json = StreamOperationsJournal.JSON.readTree(before);
        assertThat(json.path("schemaVersion").asText()).isEqualTo("SAGOPALGO_STREAM_SESSION_OBSERVATION_V1");
        assertThat(json.path("days").get(0).path("assessment").asText()).isEqualTo("OPEN_SESSION_UNOBSERVED");
        assertThat(StreamSessionObservationReport.run(args)).isEqualTo(2);
        assertThat(Files.readAllBytes(output)).isEqualTo(before);
    }

    private record RecordAt(String time, String state) {}

    private UUID journal(String start, String end, List<RecordAt> records) {
        try (var journal = new StreamOperationsJournal(true, root.toString(), 64, 65536, 262144)) {
            journal.start(UUID.randomUUID(), op(0, start, "SESSION_START", 0), ignored -> {});
            long sequence = 0;
            long elapsed = 0;
            for (var record : records) {
                Kind kind = record.state().equals("COUNTERS") ? Kind.COUNTERS : Kind.LIFECYCLE;
                if (kind == Kind.LIFECYCLE) sequence++;
                assertThat(journal.append(kind, op(sequence, record.time(), record.state(), ++elapsed))).isTrue();
            }
            assertThat(journal.finish(op(sequence, end, "SESSION_END", ++elapsed))).isTrue();
            return journal.status().sessionId();
        }
    }

    private static Operation op(long sequence, String time, String state, long elapsed) {
        return new Operation(sequence, 0, state, null, Instant.parse(time).toString(), elapsed, Counters.zero());
    }

    private static Plan plan(DayPlan... days) {
        return new Plan("SAGOPALGO_STREAM_SESSION_PLAN_V1", Source.SYNTHETIC, "005930", 2, List.of(days));
    }

    private static DayPlan open(String date) { return new DayPlan(date, OPEN, "09:00", "15:30", "SYNTHETIC_OPEN"); }
    private static DayPlan closed(String date) { return new DayPlan(date, CLOSED, null, null, "SYNTHETIC_CLOSE"); }
}
