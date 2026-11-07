package com.sagopalgo.api.market.stream;

import static com.sagopalgo.api.market.stream.StreamOperationsJournal.Kind.*;
import static org.assertj.core.api.Assertions.*;

import com.sagopalgo.api.common.util.ContentHash;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Body;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Counters;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Entry;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Kind;
import com.sagopalgo.api.market.stream.StreamOperationsJournal.Operation;
import com.sagopalgo.api.market.stream.StreamOperationsStatusReport.DurationStats;
import com.sagopalgo.api.market.stream.StreamOperationsStatusReport.Source;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class StreamOperationsStatusReportTest {
    @TempDir Path directory;

    @Test void repeatedRetriesCloseOneWindowOnlyAfterFreshDataAndUseMonotonicTime() throws Exception {
        var file = new JournalFixture();
        file.lifecycle(1, 2, "CONNECTING", null);
        file.lifecycle(1, 8, "CONNECTED", null);
        file.lifecycle(1, 10, "DATA_READY", null);
        file.lifecycle(2, 20, "RECONNECTING", "CONNECTION_CLOSED");
        file.lifecycle(3, 25, "CONNECTING", null);
        file.lifecycle(4, 29, "RECONNECTING", "CONNECT_TIMEOUT");
        file.lifecycle(5, 35, "CONNECTING", null);
        file.lifecycle(5, 40, "CONNECTED", null);
        file.counters = new Counters(3, 3, 2, 1, 0, 0, 0);
        file.add(COUNTERS, 5, 41, "COUNTERS", null);
        // Wall time reverses while this JVM's elapsed time moves forward.
        file.wallTime = "2026-11-07T00:59:00Z";
        file.lifecycle(5, 42, "DATA_READY", null);
        file.lifecycle(5, 100, "STABLE", "RETRY_BUDGET_RESET");
        file.lifecycle(6, 110, "DISABLED", "COLLECTOR_STOPPED");
        file.add(END, 6, 111, "SESSION_END", null);
        file.write();

        var report = StreamOperationsStatusReport.build(directory, null, Source.SYNTHETIC);
        var session = report.sessions().get(0);
        assertThat(report.declaredSource()).isEqualTo(Source.SYNTHETIC);
        assertThat(report.sourceProvenanceVerified()).isFalse();
        assertThat(session.lifecycleCounts()).containsEntry("CONNECTING", 3L).containsEntry("RECONNECTING", 2L);
        assertThat(session.diagnosticCounts()).containsEntry("CONNECT_TIMEOUT", 1L).containsEntry("RETRY_BUDGET_RESET", 1L);
        assertThat(session.counterCheckpoints()).isEqualTo(1);
        assertThat(session.latestCounters()).isEqualTo(file.counters);
        assertThat(session.delays().attemptToAck()).isEqualTo(new DurationStats(2, 5L, 6L));
        assertThat(session.delays().ackToDataReady()).isEqualTo(new DurationStats(2, 2L, 2L));
        assertThat(session.recovery().started()).isEqualTo(1);
        assertThat(session.recovery().timeToDataReady()).isEqualTo(new DurationStats(1, 22L, 22L));
        assertThat(session.recovery().unresolvedWindow()).isNull();
        assertThat(session.recovery().recentClosedWindows()).singleElement().satisfies(window -> {
            assertThat(window.from().generation()).isEqualTo(2);
            assertThat(window.to().generation()).isEqualTo(5);
            assertThat(window.outcome()).isEqualTo("DATA_READY_RECORDED");
        });
        assertThat(session.tail().assessment()).isEqualTo("END_MARKER_VERIFIED");
        assertThat(report.evidenceBounds().databaseRowComparison()).isEqualTo("NOT_PERFORMED");
        assertThat(report.evidenceBounds().missingProviderEvents()).isNull();
        assertThat(report.usableForTrading()).isFalse();
    }

    @ParameterizedTest
    @ValueSource(strings = {"NO_END_MARKER", "PARTIAL_TAIL", "CORRUPT"})
    void preservesIncompletePrefixWithoutInventingRecoveryOrTailCounts(String integrity) throws Exception {
        var file = new JournalFixture();
        file.lifecycle(1, 5, "CONNECTING", null);
        file.lifecycle(2, 10, "RECONNECTING", "CONNECTION_CLOSED");
        file.lifecycle(3, 15, "CONNECTING", null);
        file.lifecycle(3, 20, "CONNECTED", null);
        file.counters = new Counters(1, 1, 0, 0, 0, 0, 1);
        file.add(COUNTERS, 3, 23, "COUNTERS", null);
        switch (integrity) {
            case "PARTIAL_TAIL" -> file.lines.append("{\"entry\":");
            case "CORRUPT" -> {
                file.lines.append("{}\n");
                file.counters = new Counters(9, 9, 8, 1, 0, 0, 0);
                file.lifecycle(3, 30, "DATA_READY", null);
            }
            default -> { }
        }
        Path path = file.write();
        byte[] original = Files.readAllBytes(path);

        var report = StreamOperationsStatusReport.build(directory, file.id, Source.UNSPECIFIED);
        var session = report.sessions().get(0);
        assertThat(session.integrityStatus()).isEqualTo(integrity);
        assertThat(session.verifiedEntries()).isEqualTo(6);
        assertThat(session.lastVerified().elapsedNanos()).isEqualTo(23);
        assertThat(session.lifecycleCounts()).doesNotContainKey("DATA_READY");
        assertThat(session.latestCounters().receivedPublicFrames()).isEqualTo(1);
        assertThat(session.tail().inFlightStorage()).isEqualTo(1L);
        assertThat(session.tail().unobservedOperations()).isNull();
        assertThat(session.recovery().recovered()).isZero();
        assertThat(session.recovery().timeToDataReady()).isEqualTo(new DurationStats(0, null, null));
        assertThat(session.recovery().unresolvedWindow().from().elapsedNanos()).isEqualTo(10);
        assertThat(session.recovery().unresolvedWindow().to()).isNull();
        assertThat(session.recovery().unresolvedWindow().elapsedNanos()).isNull();
        assertThat(report.writerActivity()).isEqualTo("NOT_DETERMINED");
        assertThat(Files.readAllBytes(path)).isEqualTo(original);
    }

    @Test void unpairedAckAndDataNeverBecomeDurationSamples() throws Exception {
        var file = new JournalFixture();
        file.lifecycle(1, 1, "CONNECTING", null);
        file.lifecycle(2, 2, "CONNECTED", null);
        file.lifecycle(2, 3, "DATA_READY", null);
        file.lifecycle(3, 4, "RECONNECTING", "CONNECTION_CLOSED");
        file.lifecycle(4, 5, "CONNECTING", null);
        file.lifecycle(4, 6, "DATA_READY", null);
        file.lifecycle(5, 7, "FAILED", "CONNECTION_FAILED");
        file.add(END, 5, 8, "SESSION_END", null);
        file.write();

        var session = StreamOperationsStatusReport.build(directory, null, Source.SYNTHETIC).sessions().get(0);
        assertThat(session.delays().unpairedAcks()).isEqualTo(1);
        assertThat(session.delays().unpairedDataReady()).isEqualTo(2);
        assertThat(session.delays().attemptToAck().samples()).isZero();
        assertThat(session.delays().ackToDataReady().samples()).isZero();
        assertThat(session.recovery().endedWithoutDataReady()).isEqualTo(1);
        assertThat(session.recovery().recovered()).isZero();
        assertThat(session.recovery().recentClosedWindows().get(0).outcome()).isEqualTo("ENDED_BEFORE_DATA_READY");
        assertThat(session.recovery().unresolvedWindow()).isNull();
    }

    @Test void sessionsStaySeparateAndEndWithInFlightStorageRemainsVisible() throws Exception {
        var prior = new JournalFixture();
        prior.lifecycle(1, 2, "RECONNECTING", "HEARTBEAT_TIMEOUT");
        prior.write();
        var next = new JournalFixture();
        next.lifecycle(1, 1, "CONNECTING", null);
        next.lifecycle(1, 2, "CONNECTED", null);
        next.lifecycle(1, 3, "DATA_READY", null);
        next.counters = new Counters(4, 4, 3, 0, 0, 0, 1);
        next.add(END, 2, 4, "SESSION_END", null);
        next.write();

        var report = StreamOperationsStatusReport.build(directory, null, Source.CAPTURE);
        assertThat(report.crossSessionOrder()).isEqualTo("UNCONFIRMED");
        assertThat(report.sourceProvenanceVerified()).isFalse();
        assertThat(report.sessions()).hasSize(2);
        assertThat(report.sessions()).filteredOn(session -> session.sessionId().equals(prior.id)).singleElement()
            .satisfies(session -> assertThat(session.recovery().unresolvedWindow()).isNotNull());
        var selected = StreamOperationsStatusReport.build(directory, next.id, Source.CAPTURE).sessions();
        assertThat(selected).singleElement().satisfies(session -> {
            assertThat(session.clockDomain()).isEqualTo(next.domain).isNotEqualTo(prior.domain);
            assertThat(session.recovery().started()).isZero();
            assertThat(session.recovery().recovered()).isZero();
            assertThat(session.integrityStatus()).isEqualTo("CLEAN_END");
            assertThat(session.tail().assessment()).isEqualTo("END_WITH_IN_FLIGHT_STORAGE");
            assertThat(session.tail().inFlightStorage()).isEqualTo(1L);
        });
    }

    @Test void aggregatesBeyondInspectorPageLimitWithBoundedRecoveryDetails() throws Exception {
        var file = new JournalFixture();
        for (int i = 1; i <= 1001; i++) file.add(COUNTERS, 0, i, "COUNTERS", null);
        for (int i = 0; i < 18; i++) {
            long elapsed = 1100 + i * 5;
            long generation = 2L * i + 1;
            file.lifecycle(generation, elapsed, "RECONNECTING", "CONNECTION_CLOSED");
            file.lifecycle(generation + 1, elapsed + 1, "CONNECTING", null);
            file.lifecycle(generation + 1, elapsed + 2, "CONNECTED", null);
            file.lifecycle(generation + 1, elapsed + 3, "DATA_READY", null);
        }
        file.add(END, 37, 1200, "SESSION_END", null);
        file.write();

        var session = StreamOperationsStatusReport.build(directory, file.id, Source.SYNTHETIC).sessions().get(0);
        assertThat(session.verifiedEntries()).isEqualTo(1075);
        assertThat(session.counterCheckpoints()).isEqualTo(1001);
        assertThat(session.recovery().recovered()).isEqualTo(18);
        assertThat(session.recovery().timeToDataReady()).isEqualTo(new DurationStats(18, 3L, 3L));
        assertThat(session.recovery().recentClosedWindows()).hasSize(16);
        assertThat(session.recovery().olderClosedWindowsOmitted()).isEqualTo(2);
        assertThat(session.recovery().recentClosedWindows().get(0).from().elapsedNanos()).isEqualTo(1110);
    }

    @Test void emptyInputNeverCreatesAnObservedZeroSnapshot() throws Exception {
        assertThat(StreamOperationsStatusReport.build(directory, null, Source.UNSPECIFIED).sessions()).isEmpty();
        UUID id = UUID.randomUUID();
        Files.createFile(directory.resolve("session-" + id + ".jsonl"));
        var session = StreamOperationsStatusReport.build(directory, id, Source.UNSPECIFIED).sessions().get(0);
        assertThat(session.verifiedEntries()).isZero();
        assertThat(session.integrityStatus()).isEqualTo("EMPTY");
        assertThat(session.latestCounters()).isNull();
        assertThat(session.firstVerified()).isNull();
        assertThat(session.tail().assessment()).isEqualTo("NO_RECORDS");
    }

    @Test void cliWritesNewReportOnlyAndRejectsAnUnrecognizedSource() throws Exception {
        var file = new JournalFixture();
        Path input = file.write();
        byte[] original = Files.readAllBytes(input);
        Path output = directory.resolve("report.json");
        var args = new String[] {"--directory", directory.toString(), "--output", output.toString(), "--source", "SYNTHETIC"};
        assertThat(StreamOperationsStatusReport.run(args)).isZero();
        byte[] published = Files.readAllBytes(output);
        var json = StreamOperationsJournal.JSON.readTree(published);
        assertThat(json.get("schemaVersion").asText()).isEqualTo("SAGOPALGO_STREAM_OPERATIONS_STATUS_V1");
        assertThat(json.get("sessions").get(0).get("tail").get("assessment").asText()).isEqualTo("END_NOT_VERIFIED");
        assertThat(StreamOperationsStatusReport.run(args)).isEqualTo(2);
        assertThat(Files.readAllBytes(output)).isEqualTo(published);
        args[3] = directory.resolve("invalid.json").toString();
        args[5] = "LIVE_VERIFIED";
        assertThat(StreamOperationsStatusReport.run(args)).isEqualTo(2);
        assertThat(directory.resolve("invalid.json")).doesNotExist();
        assertThat(Files.readAllBytes(input)).isEqualTo(original);
    }

    private final class JournalFixture {
        final UUID id = UUID.randomUUID();
        final UUID domain = UUID.randomUUID();
        final StringBuilder lines = new StringBuilder();
        String wallTime = "2026-11-07T01:00:00Z";
        String previous = StreamOperationsJournal.ZERO;
        long index;
        long sequence;
        Counters counters = Counters.zero();

        JournalFixture() throws IOException {
            add(START, 0, 0, "SESSION_START", null);
        }

        void lifecycle(long generation, long elapsed, String state, String code) throws IOException {
            add(LIFECYCLE, generation, elapsed, state, code);
        }

        void add(Kind kind, long generation, long elapsed, String state, String code) throws IOException {
            if (kind == LIFECYCLE) sequence++;
            var operation = new Operation(sequence, generation, state, code, wallTime, elapsed, counters);
            var body = new Body(StreamOperationsJournal.VERSION, id, domain, false, ++index, kind, operation, previous);
            previous = ContentHash.sha256(StreamOperationsJournal.JSON.writeValueAsString(body));
            lines.append(StreamOperationsJournal.JSON.writeValueAsString(new Entry(body, previous))).append('\n');
        }

        Path write() throws IOException {
            return Files.writeString(directory.resolve("session-" + id + ".jsonl"), lines);
        }
    }
}
