package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.research.export.StoredDatasetExportService;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/** Real loopback socket and marked/tmpfs MySQL; frames and approval are synthetic. */
@EnabledIfEnvironmentVariable(named="SAGOPALGO_MARKET_RESEARCH_MYSQL_TEST",matches="true")
class KisStreamSocketMysqlIntegrationTest {
    @Test void reconnectPreservesCommittedRowsDeduplicatesReplayAndExportsUnfilledGap() throws Exception {
        var data=new MarketResearchMysqlIntegrationTest();
        data.initializeOnlyMarkedDatabase();
        data.json.disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        data.resetOnlyTestFixtures();
        try(var fixture=new KisStreamSocketRecoveryTest.Fixture(KisStreamSocketRecoveryTest.timing(),data.stream)) {
            fixture.start();var first=fixture.server.next();fixture.subscriptions(first,true);
            first.text(KisStreamSocketRecoveryTest.trade("1"));first.text(MarketStreamTest.quote());
            KisStreamSocketRecoveryTest.until(()->fixture.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).state().equals("LIVE"));
            first.reset();var second=fixture.server.next();fixture.subscriptions(second,true);
            KisStreamSocketRecoveryTest.until(()->fixture.state().equals("CONNECTED"));
            assertThat(fixture.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).trade()).isNull();
            second.text(KisStreamSocketRecoveryTest.trade("1")); // same event, no second volume contribution
            second.text(KisStreamSocketRecoveryTest.trade("4"));
            second.text(MarketStreamTest.quote().replace("100001","100004"));
            KisStreamSocketRecoveryTest.until(()->{
                var tick=fixture.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).trade();
                return tick!=null && tick.cumulativeVolume().equals("4");
            });
            assertThat(data.jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_events WHERE event_type='TRADE'",Integer.class)).isEqualTo(2);
            var bars=data.stream.minutes("005930",KisStreamSocketRecoveryTest.NOW.minusSeconds(60));
            assertThat(bars).hasSize(1);assertThat(bars.get(0).volume()).isEqualTo("2");
            assertThat(bars.get(0).trades()).isEqualTo(2);assertThat(bars.get(0).coverage()).isEqualTo("OBSERVED_ONLY");
            var exported=data.proxy(new StoredDatasetExportService(data.jdbc,KisStreamSocketRecoveryTest.JSON))
                .export("005930",Instant.parse("2026-11-06T01:00:00Z"),Instant.parse("2026-11-06T01:01:00Z"));
            assertThat(exported.streamCoverage()).isEqualTo("OBSERVED_ONLY");
            assertThat(exported.streamEvents().stream().filter(e->e.type().equals("TRADE")).count()).isEqualTo(2);
            assertThat(KisStreamSocketRecoveryTest.JSON.readTree(exported.streamEvents().get(0).payloadJson()).path("marketTime").isTextual()).isTrue();
            fixture.connection.stop();
            Path directory=Path.of("build-codex-socket-recovery");Files.createDirectories(directory);
            String run=UUID.randomUUID().toString();
            Files.write(directory.resolve("socket-mysql-export-"+run+".json"),
                KisStreamSocketRecoveryTest.JSON.writeValueAsBytes(ApiResponse.success(exported,"SYNTHETIC_SOCKET_MYSQL_TEST_ONLY")),StandardOpenOption.CREATE_NEW);
            Files.write(directory.resolve("socket-mysql-receipt-"+run+".json"),
                KisStreamSocketRecoveryTest.JSON.writeValueAsBytes(Map.of("source","LOOPBACK_AND_ISOLATED_MYSQL_SYNTHETIC_FRAMES",
                    "recovery",fixture.connection.recoverySnapshot(),"observedTradeRows",2,"observedVolume","2",
                    "cumulativeBefore","1","cumulativeAfter","4","missingTradesReconstructed",false)),StandardOpenOption.CREATE_NEW);
        }
    }
}
