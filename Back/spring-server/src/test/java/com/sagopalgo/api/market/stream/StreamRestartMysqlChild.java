package com.sagopalgo.api.market.stream;

import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/** Test subprocess only. It uses the same collector and marked MySQL transaction proxy. */
public final class StreamRestartMysqlChild {
    static final String TRADE_1 = KisStreamSocketRecoveryTest.trade("1");
    static final String TRADE_4 = KisStreamSocketRecoveryTest.trade("4");
    static final String TRADE_7 = MarketStreamTest.trade("100005", "103", "1", "7").replace("20261103", "20261106");
    static final String QUOTE_1 = MarketStreamTest.quote();
    static final String QUOTE_7 = QUOTE_1.replace("100001", "100005");
    static final String ENABLE = "SAGOPALGO_MARKET_RESEARCH_MYSQL_TEST";

    public static void main(String[] args) throws Exception {
        if (!"true".equals(System.getenv(ENABLE)) || args.length != 2
            || !List.of("rollback", "commit-crash", "replay").contains(args[0])) {
            throw new IllegalArgumentException("ISOLATED_RESTART_FIXTURE_REQUIRED");
        }
        String mode = args[0];
        Path directory = Path.of(args[1]);
        var data = new MarketResearchMysqlIntegrationTest();
        data.initializeOnlyMarkedDatabase();
        data.json.disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        var store = data.proxy(new MarketStreamStore(data.session.getMapper(MarketStreamMapper.class), data.json));
        var committed = new CountDownLatch(1);
        var stopAfterCommit = new CountDownLatch(1);
        var journal = new StreamOperationsJournal(true, directory.toString(), 64, 65536, 262144);
        MarketStreamStore collectorStore = mode.equals("commit-crash") ? new MarketStreamStore(null, data.json) {
            @Override public void verify() { store.verify(); }
            @Override public List<StreamMinuteBar> minutes(String stock, java.time.Instant from) {
                return store.minutes(stock, from);
            }
            @Override public boolean appendCommitted(MarketStreamEvent event, Runnable afterCommit) {
                boolean added = store.appendCommitted(event, afterCommit);
                if (added && "4".equals(event.cumulativeVolume())) {
                    committed.countDown();
                    try {
                        if (!stopAfterCommit.await(20, TimeUnit.SECONDS)) throw new IllegalStateException("HALT_NOT_OBSERVED");
                    } catch (InterruptedException error) {
                        Thread.currentThread().interrupt();
                        throw new IllegalStateException("FIXTURE_INTERRUPTED", error);
                    }
                }
                return added;
            }
        } : store;

        var timing = new KisStreamConnection.Timing(Duration.ofSeconds(12), Duration.ofSeconds(5), Duration.ofSeconds(4),
            Duration.ofSeconds(2), Duration.ofMillis(20), Duration.ofMillis(40), Duration.ofMillis(50),
            Duration.ofSeconds(1), Duration.ofSeconds(3));
        try (var fixture = new KisStreamSocketRecoveryTest.Fixture(timing, collectorStore, new LoopbackWebSocketServer(),
            Clock.fixed(KisStreamSocketRecoveryTest.NOW, ZoneOffset.UTC), journal)) {
            fixture.start();
            var peer = fixture.server.next();
            fixture.subscriptions(peer, true);
            peer.text(TRADE_1);
            peer.text(QUOTE_1);
            if (!mode.equals("replay")) {
                KisStreamSocketRecoveryTest.until(() -> fixture.hub.freshInputs(KisStreamSocketRecoveryTest.NOW));
            }
            peer.text(TRADE_4);
            if (mode.equals("replay")) {
                peer.text(TRADE_7);
                peer.text(QUOTE_7);
                KisStreamSocketRecoveryTest.until(() -> fixture.connection.recoverySnapshot().counters().decodedEvents() == 5
                    && fixture.hub.freshInputs(KisStreamSocketRecoveryTest.NOW)
                    && fixture.connection.recoverySnapshot().counters().storageInsertions()
                        + fixture.connection.recoverySnapshot().counters().nonInsertions() == 5);
            } else {
                if (mode.equals("commit-crash") && !committed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("COMMIT_NOT_OBSERVED");
                }
                awaitDurableBoundary(directory, mode);
                Runtime.getRuntime().halt(0);
            }
        } finally {
            stopAfterCommit.countDown();
        }
    }

    private static void awaitDurableBoundary(Path directory, String mode) throws Exception {
        long deadline = System.nanoTime() + Duration.ofSeconds(5).toNanos();
        while (System.nanoTime() < deadline) {
            var scans = StreamOperationsJournalInspector.scanDirectory(directory, null, entry -> {});
            if (scans.size() == 1 && scans.get(0).lastOperation() != null) {
                var operation = scans.get(0).lastOperation();
                var counters = operation.counters();
                if (mode.equals("rollback") && "FAILED".equals(operation.state()) && counters.storageFailures() == 1) return;
                if (mode.equals("commit-crash") && "COUNTERS".equals(operation.state())
                    && counters.inFlightStorage() == 1 && counters.storageInsertions() == 2) return;
            }
            Thread.sleep(20);
        }
        throw new IllegalStateException("DURABLE_TEST_BOUNDARY_NOT_OBSERVED");
    }
}
