package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@EnabledIfEnvironmentVariable(named = StreamRestartMysqlChild.ENABLE, matches = "true")
class StreamRestartMysqlIntegrationTest {
    private record InputFrame(String sha256, String text, MarketStreamEvent event) {}
    private record DbRow(String id, String payloadSha256, MarketStreamEvent event) {}
    private record Evidence(String source, String scenario, UUID failedSession, UUID replaySession,
                            List<InputFrame> original, List<DbRow> afterFailure, List<DbRow> afterReplay,
                            String faultTradeOutcome, String minuteVolume, long minuteTrades,
                            StreamOperationsStatusReport.Report journal, Long unobservedOperations) {}

    @ParameterizedTest
    @ValueSource(strings = {"rollback", "commit-crash"})
    void comparesSourceRowsAndJournalAcrossTwoActualProcesses(String mode) throws Exception {
        var data = new MarketResearchMysqlIntegrationTest();
        data.initializeOnlyMarkedDatabase();
        data.resetOnlyTestFixtures();
        Path root = Files.createDirectories(Path.of("build-codex-u07", "restart"));
        Path run = Files.createTempDirectory(root, mode + "-").toAbsolutePath();
        Path journal = run.resolve("journal");
        boolean rollback = mode.equals("rollback");
        var source = original();
        if (rollback) {
            data.jdbc.execute("CREATE TRIGGER u07_restart_fail_update BEFORE UPDATE ON market_stream_minutes FOR EACH ROW "
                + "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='U07_RESTART_TEST_ONLY'");
        }
        try {
            child(mode, run, journal);
        } finally {
            if (rollback) data.jdbc.execute("DROP TRIGGER u07_restart_fail_update");
        }
        var afterFailure = rows(data);
        compareRows(afterFailure, source.subList(0, rollback ? 2 : 3));
        var before = StreamOperationsJournalInspector.scanDirectory(journal, null, entry -> {});
        assertThat(before).hasSize(1);
        var first = before.get(0);
        assertThat(first.status()).isEqualTo("NO_END_MARKER");
        assertThat(first.lastOperation().counters().storageInsertions()).isEqualTo(2);
        assertThat(first.lastOperation().counters().storageFailures()).isEqualTo(rollback ? 1 : 0);
        assertThat(first.lastOperation().counters().inFlightStorage()).isEqualTo(rollback ? 0 : 1);
        Path firstPath = journal.resolve("session-" + first.sessionId() + ".jsonl");
        byte[] firstBytes = Files.readAllBytes(firstPath);

        child("replay", run, journal);
        var afterReplay = rows(data);
        compareRows(afterReplay, source);
        assertThat(afterReplay).containsAll(afterFailure);
        assertThat(Files.readAllBytes(firstPath)).isEqualTo(firstBytes);
        var report = StreamOperationsStatusReport.build(journal, null, StreamOperationsStatusReport.Source.SYNTHETIC);
        assertThat(report.sessions()).hasSize(2);
        var replay = report.sessions().stream().filter(s -> !s.sessionId().equals(first.sessionId())).findFirst().orElseThrow();
        assertThat(replay.integrityStatus()).isEqualTo("CLEAN_END");
        assertThat(replay.clockDomain()).isNotEqualTo(first.clockDomain());
        assertThat(replay.latestCounters().storageInsertions()).isEqualTo(rollback ? 3 : 2);
        assertThat(replay.latestCounters().nonInsertions()).isEqualTo(rollback ? 2 : 3);
        assertThat(replay.latestCounters().inFlightStorage()).isZero();
        var bars = data.stream.minutes("005930", KisStreamSocketRecoveryTest.NOW.minusSeconds(60));
        assertThat(bars).hasSize(1);
        assertThat(bars.get(0).volume()).isEqualTo("3");
        assertThat(bars.get(0).trades()).isEqualTo(3);
        assertThat(bars.get(0).coverage()).isEqualTo("OBSERVED_ONLY");
        var evidence = new Evidence("LOOPBACK_SYNTHETIC_MARKED_MYSQL_TWO_JVMS", mode, first.sessionId(), replay.sessionId(),
            source, afterFailure, afterReplay, rollback ? "ROLLED_BACK" : "COMMITTED_BEFORE_RECEIPT",
            bars.get(0).volume(), bars.get(0).trades(), report, null);
        Files.write(run.resolve("comparison.json"), KisStreamSocketRecoveryTest.JSON.writeValueAsBytes(evidence));
    }

    private static List<InputFrame> original() {
        var decoder = new KisStreamDecoder();
        return List.of(StreamRestartMysqlChild.TRADE_1, StreamRestartMysqlChild.QUOTE_1, StreamRestartMysqlChild.TRADE_4,
            StreamRestartMysqlChild.TRADE_7, StreamRestartMysqlChild.QUOTE_7).stream()
            .map(frame -> new InputFrame(KisStreamDecoder.hash(frame), frame,
                decoder.decode(frame, KisStreamSocketRecoveryTest.NOW).get(0))).toList();
    }

    private static List<DbRow> rows(MarketResearchMysqlIntegrationTest data) {
        return data.jdbc.query("SELECT event_id,payload FROM market_stream_events ORDER BY event_id", (row, index) -> {
            String payload = row.getString("payload");
            try {
                return new DbRow(row.getString("event_id"), KisStreamDecoder.hash(payload),
                    KisStreamSocketRecoveryTest.JSON.readValue(payload, MarketStreamEvent.class));
            } catch (java.io.IOException error) {
                throw new java.sql.SQLException("INVALID_TEST_EVENT_PAYLOAD", error);
            }
        });
    }

    private static void compareRows(List<DbRow> actual, List<InputFrame> source) {
        assertThat(actual).extracting(DbRow::id).containsExactlyInAnyOrderElementsOf(source.stream()
            .map(input -> input.event().eventId()).toList());
        assertThat(actual).extracting(DbRow::event).containsExactlyInAnyOrderElementsOf(source.stream()
            .map(InputFrame::event).toList());
    }

    private static void child(String mode, Path run, Path journal) throws Exception {
        String classpath = System.getProperty("sagopalgo.test.runtimeClasspath");
        assertThat(classpath).isNotBlank();
        Path argFile = run.resolve(mode + ".args");
        Files.writeString(argFile, "-cp\n" + quoted(classpath) + "\n" + StreamRestartMysqlChild.class.getName()
            + "\n" + mode + "\n" + quoted(journal.toString()) + "\n", StandardCharsets.UTF_8);
        boolean windows = System.getProperty("os.name").toLowerCase(Locale.ROOT).contains("win");
        Path java = Path.of(System.getProperty("java.home"), "bin", windows ? "java.exe" : "java");
        Path log = run.resolve(mode + ".log");
        var process = new ProcessBuilder(java.toString(), "@" + argFile).redirectErrorStream(true)
            .redirectOutput(log.toFile()).start();
        try {
            assertThat(process.waitFor(35, TimeUnit.SECONDS)).as("child timeout, %s", log).isTrue();
            assertThat(process.exitValue()).as("child failure, %s", log).isZero();
        } finally {
            if (process.isAlive()) {
                process.destroyForcibly();
                process.waitFor(5, TimeUnit.SECONDS);
            }
        }
    }

    private static String quoted(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
