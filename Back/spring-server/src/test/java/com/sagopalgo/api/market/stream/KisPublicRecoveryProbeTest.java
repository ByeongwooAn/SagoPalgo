package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.config.KisMarketProperties;
import java.io.ByteArrayInputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class KisPublicRecoveryProbeTest {
    @TempDir Path output;

    @Test void realRelayResetRecoversBothSubscriptionsAndRetainsPublicEvidence() throws Exception {
        try (var server = new LoopbackWebSocketServer()) {
            var worker = Executors.newSingleThreadExecutor();
            var approval = new ApprovalFixture();
            try {
                var pending = worker.submit(() -> execute(server, approval, Duration.ofSeconds(4)));
                var first = server.next();
                subscribe(first);
                first.fragmented(KisStreamSocketRecoveryTest.trade("1"));
                first.text(MarketStreamTest.quote());

                var second = server.next();
                subscribe(second);
                second.text(KisStreamSocketRecoveryTest.trade("1"));
                second.text(MarketStreamTest.quote());
                second.text(KisStreamSocketRecoveryTest.trade("4"));
                second.text(MarketStreamTest.quote().replace("100001", "100004"));

                var result = pending.get(8, TimeUnit.SECONDS);
                approval.mock.verify();
                assertThat(result.status()).as("probe failure code %s", result.failureCode()).isEqualTo("RECOVERY_OBSERVED");
                assertThat(result.source()).isEqualTo("LOOPBACK_SYNTHETIC");
                assertThat(result.before().generation()).isLessThan(result.after().generation());
                assertThat(result.before().trade().cumulativeVolume()).isEqualTo("1");
                assertThat(result.after().trade().cumulativeVolume()).isEqualTo("4");
                assertThat(result.approvals()).isEqualTo(1);
                assertThat(result.upstreamDials()).isEqualTo(2).isEqualTo(result.dialsAtStop());
                assertThat(result.tunnelArrivals()).isEqualTo(2).isEqualTo(result.arrivalsAtStop());
                assertThat(server.accepted()).isEqualTo(2);
                assertThat(result.duplicates()).isEqualTo(2);
                assertThat(result.uniqueEvents()).isEqualTo(4);
                assertThat(result.stableResetObserved()).isFalse();
                assertThat(result.journalCleanEnd()).isTrue();
                assertThat(result.volumeBoundary().unobservedVolume()).isEqualTo("2");
                assertThat(result.volumeBoundary().lastBeforeEventId()).isEqualTo(result.before().trade().eventId());
                assertThat(result.volumeBoundary().firstAfterEventId()).isEqualTo(result.after().trade().eventId());
                assertThat(result.stopped().stopped()).isTrue();
                assertThat(result.stopped().failures()).isEqualTo(1);
                assertThat(result.stopped().receipts()).anyMatch(receipt -> "RECONNECTING".equals(receipt.state()));
                assertThat(result.usableForTrading()).isFalse();

                var file = Files.readString(output.resolve("public-frames.json"));
                assertThat(file).doesNotContain("synthetic-approval-only", "test-only-secret", "rt_cd");
                var frames = KisStreamSocketRecoveryTest.JSON.readTree(file);
                assertThat(frames).hasSize(6);
                var decoder = new KisStreamDecoder();
                for (var frame : frames) {
                    String text = frame.path("publicFrame").asText();
                    assertThat(frame.path("frameSha256").asText()).isEqualTo(KisStreamDecoder.hash(text));
                    var events = decoder.decode(text, Instant.parse(frame.path("receivedAt").asText()));
                    assertThat(frame.path("eventIds").get(0).asText()).isEqualTo(events.get(0).eventId());
                }
                var journal = StreamOperationsStatusReport.build(output.resolve("journal"), null,
                    StreamOperationsStatusReport.Source.SYNTHETIC);
                assertThat(journal.sessions()).singleElement().satisfies(session -> {
                    assertThat(session.recovery().recovered()).isEqualTo(1);
                    assertThat(session.latestCounters().storageInsertions()).isEqualTo(4);
                    assertThat(session.latestCounters().nonInsertions()).isEqualTo(2);
                });
            } finally {
                worker.shutdownNow();
            }
        }
    }

    @Test void absentBaselineDataEndsWithoutInjectingAnyFault() throws Exception {
        try (var server = new LoopbackWebSocketServer()) {
            var worker = Executors.newSingleThreadExecutor();
            var approval = new ApprovalFixture();
            try {
                var pending = worker.submit(() -> execute(server, approval, Duration.ofMillis(900)));
                subscribe(server.next());
                var result = pending.get(5, TimeUnit.SECONDS);
                approval.mock.verify();
                assertThat(result.status()).isEqualTo("INCONCLUSIVE");
                assertThat(result.failureCode()).isEqualTo("PROBE_BASELINE_TIMEOUT");
                assertThat(result.faultInjectedAt()).isNull();
                assertThat(result.upstreamDials()).isEqualTo(1);
                assertThat(result.journalCleanEnd()).isTrue();
            } finally {
                worker.shutdownNow();
            }
        }
    }

    @Test void relayBlocksAThirdUpstreamDial() throws Exception {
        try (var server = new LoopbackWebSocketServer(); var relay = new KisProbeTunnel(server.endpoint())) {
            var client = HttpClient.newHttpClient();
            for (int i = 0; i < 2; i++) {
                var socket = client.newWebSocketBuilder().buildAsync(relay.endpoint(), new WebSocket.Listener() {})
                    .get(3, TimeUnit.SECONDS);
                server.next();
                socket.abort();
            }
            assertThatThrownBy(() -> client.newWebSocketBuilder().buildAsync(relay.endpoint(), new WebSocket.Listener() {})
                .get(3, TimeUnit.SECONDS)).isInstanceOf(java.util.concurrent.ExecutionException.class);
            // HttpClient can retry the rejected local handshake. Neither attempt may reach the upstream.
            assertThat(relay.arrivals()).isGreaterThanOrEqualTo(3);
            assertThat(relay.upstreamDials()).isEqualTo(2);
            assertThat(server.accepted()).isEqualTo(2);
        }
    }

    @Test void rewritesOnlyHostAndLeavesFollowingBytesInInput() throws Exception {
        var input = new ByteArrayInputStream(("GET /tryitout HTTP/1.1\r\nHost: 127.0.0.1:12345\r\n"
            + "Sec-WebSocket-Key: test\r\n\r\nunchanged").getBytes(StandardCharsets.US_ASCII));
        var header = KisProbeTunnel.relayHandshake(input, URI.create("ws://upstream.example:21000/tryitout"));
        assertThat(new String(header, StandardCharsets.US_ASCII))
            .isEqualTo("GET /tryitout HTTP/1.1\r\nHost: upstream.example:21000\r\nSec-WebSocket-Key: test\r\n\r\n");
        assertThat(new String(input.readAllBytes(), StandardCharsets.US_ASCII)).isEqualTo("unchanged");
    }

    @ParameterizedTest
    @ValueSource(strings = {"2026-11-07T01:00:00Z", "2026-11-09T00:04:59Z", "2026-11-09T06:17:00Z", "2026-11-10T01:00:00Z"})
    void dateAndIntradayWindowFailClosed(String instant) {
        var date = instant.startsWith("2026-11-07") ? LocalDate.of(2026, 11, 7) : LocalDate.of(2026, 11, 9);
        var clock = Clock.fixed(Instant.parse(instant), ZoneOffset.UTC);
        assertThatThrownBy(() -> KisPublicRecoveryProbe.requireWindow(date, clock))
            .hasMessage("OUTSIDE_CONFIRMED_KRX_WINDOW");
    }

    @Test void weekdayWindowRequiresExplicitOperatorConfirmationsBeforeAnyAccess() {
        var clock = Clock.fixed(Instant.parse("2026-11-09T01:00:00Z"), ZoneOffset.UTC);
        assertThatCode(() -> KisPublicRecoveryProbe.requireWindow(LocalDate.of(2026, 11, 9), clock))
            .doesNotThrowAnyException();
        assertThat(KisPublicRecoveryProbe.launch(new String[]{"--market-date", "2026-11-09", "--stock-code", "005930"}, clock))
            .isEqualTo(2);
    }

    private KisPublicRecoveryProbe.Result execute(LoopbackWebSocketServer server, ApprovalFixture approval,
                                                  Duration beforeLimit) throws Exception {
        var timing = new KisStreamConnection.Timing(Duration.ofSeconds(3), Duration.ofSeconds(2), Duration.ofSeconds(2),
            Duration.ofSeconds(1), Duration.ofMillis(20), Duration.ofMillis(20), Duration.ofMillis(50),
            Duration.ofMillis(100), Duration.ofSeconds(10));
        return KisPublicRecoveryProbe.run(output, "005930", server.endpoint(), approval.kis, approval.client,
            Clock.fixed(KisStreamSocketRecoveryTest.NOW, ZoneOffset.UTC), timing, beforeLimit, Duration.ofSeconds(4),
            Duration.ofMillis(150), approval.calls, "LOOPBACK_SYNTHETIC");
    }

    private static void subscribe(LoopbackWebSocketServer.Peer peer) throws Exception {
        for (String id : List.of("H0STCNT0", "H0STASP0")) {
            var request = KisStreamSocketRecoveryTest.JSON.readTree(peer.frame(1).text());
            var subscription = request.path("body").path("input");
            assertThat(subscription.path("tr_id").asText()).isEqualTo(id);
            assertThat(subscription.path("tr_key").asText()).isEqualTo("005930");
            peer.text(KisStreamSocketRecoveryTest.ack(id, "0"));
        }
    }

    private static final class ApprovalFixture {
        final KisMarketProperties kis = new KisMarketProperties();
        final AtomicInteger calls = new AtomicInteger();
        final MockRestServiceServer mock;
        final RestClient client;
        ApprovalFixture() {
            kis.setEnabled(true);
            kis.setAppKey("test-only-key");
            kis.setAppSecret("test-only-secret");
            var builder = RestClient.builder();
            mock = MockRestServiceServer.bindTo(builder).build();
            mock.expect(requestTo("https://openapi.koreainvestment.com:9443/oauth2/Approval"))
                .andRespond(request -> {
                    calls.incrementAndGet();
                    return withSuccess("{\"approval_key\":\"synthetic-approval-only\"}", MediaType.APPLICATION_JSON)
                        .createResponse(request);
                });
            client = builder.build();
        }
    }
}
