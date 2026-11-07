package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.*;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.function.BooleanSupplier;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class KisStreamSocketRecoveryTest {
    static final Instant NOW=Instant.parse("2026-11-06T01:00:05Z");
    static final ObjectMapper JSON=new ObjectMapper().findAndRegisterModules()
        .disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    final List<Map<String,Object>> receipts=new ArrayList<>();
    static KisStreamConnection.Timing timing() {
        return new KisStreamConnection.Timing(Duration.ofMillis(900),Duration.ofMillis(500),Duration.ofSeconds(2),
            Duration.ofMillis(700),Duration.ofMillis(20),Duration.ofMillis(10),Duration.ofMillis(30),Duration.ofMillis(80),Duration.ofMillis(200));
    }
    static String trade(String cumulative) {return MarketStreamTest.trade("10000"+(cumulative.equals("1")?"1":"4"),"101","1",cumulative).replace("20261103","20261106");}
    static void until(BooleanSupplier condition) throws InterruptedException {
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
        while(!condition.getAsBoolean() && System.nanoTime()<deadline)Thread.sleep(5);
        assertThat(condition.getAsBoolean()).as("bounded socket condition").isTrue();
    }
    static final class Fixture implements AutoCloseable {
        final LoopbackWebSocketServer server;
        final MarketStreamStore store;
        final Map<String,MarketStreamEvent> events=new ConcurrentHashMap<>();
        final MarketStreamHub hub;
        final MockRestServiceServer approval;
        final KisStreamConnection connection;
        Fixture() throws Exception {this(timing(),null);}
        Fixture(KisStreamConnection.Timing timing) throws Exception {this(timing,null);}
        Fixture(KisStreamConnection.Timing timing,MarketStreamStore actualStore) throws Exception {
            this(timing,actualStore,new LoopbackWebSocketServer());
        }
        Fixture(KisStreamConnection.Timing timing,MarketStreamStore actualStore,LoopbackWebSocketServer server) throws Exception {
            this(timing,actualStore,server,Clock.fixed(NOW,ZoneOffset.UTC));
        }
        Fixture(KisStreamConnection.Timing timing,MarketStreamStore actualStore,LoopbackWebSocketServer server,Clock clock) throws Exception {
            this(timing,actualStore,server,clock,StreamOperationsJournal.disabled());
        }
        Fixture(KisStreamConnection.Timing timing,MarketStreamStore actualStore,LoopbackWebSocketServer server,Clock clock,StreamOperationsJournal journal) throws Exception {
            this.server=server;
            store=actualStore==null?mock(MarketStreamStore.class):actualStore;
            hub=new MarketStreamHub(MarketStreamTest.enabled(),store);
            if(actualStore==null) {
            when(store.minutes(any(),any())).thenReturn(List.of());
            // Storage contract fake only; the dedicated MySQL test covers real commit/dedup.
            when(store.appendCommitted(any(),any())).thenAnswer(call->{
                MarketStreamEvent event=call.getArgument(0);
                if(events.putIfAbsent(event.eventId(),event)!=null)return false;
                ((Runnable)call.getArgument(1)).run();return true;
            });
            }
            var kis=new KisMarketProperties();kis.setEnabled(true);kis.setAppKey("test-only-key");kis.setAppSecret("test-only-secret");
            var builder=RestClient.builder();approval=MockRestServiceServer.bindTo(builder).build();
            approval.expect(requestTo("https://openapi.koreainvestment.com:9443/oauth2/Approval"))
                .andRespond(withSuccess("{\"approval_key\":\"synthetic-approval-only\"}",MediaType.APPLICATION_JSON));
            connection=new KisStreamConnection(kis,MarketStreamTest.enabled(),hub,builder.build(),JSON,
                HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(2)).build(),server.endpoint(),timing,clock,journal);
        }
        void start() {connection.start();}
        void subscriptions(LoopbackWebSocketServer.Peer peer,boolean quoteAck) throws Exception {
            for(String expected:List.of("H0STCNT0","H0STASP0")) {
                var message=JSON.readTree(peer.frame(1).text());
                assertThat(message.path("body").path("input").path("tr_id").asText()).isEqualTo(expected);
                assertThat(message.path("body").path("input").path("tr_key").asText()).isEqualTo("005930");
                assertThat(message.path("header").path("tr_type").asText()).isEqualTo("1");
                if(quoteAck || expected.equals("H0STCNT0"))peer.text(ack(expected,"0"));
            }
        }
        String state() {return hub.snapshot("005930",NOW).connectionState();}
        @Override public void close() throws Exception {connection.stop();server.close();approval.verify();}
    }
    static String ack(String tr,String result) {
        return "{\"header\":{\"tr_id\":\""+tr+"\",\"tr_key\":\"005930\"},\"body\":{\"rt_cd\":\""+result+"\"}}";
    }
    void record(String name,Fixture fixture) {
        receipts.add(Map.of("case",name,"source","LOOPBACK_REAL_TCP_SYNTHETIC_FRAMES", "acceptedSockets",fixture.server.accepted(),
            "recovery",fixture.connection.recoverySnapshot(),"accountOrProviderConnection",false));
    }
    @AfterAll void saveReceipts() throws Exception {
        Path directory=Path.of("build-codex-socket-recovery");Files.createDirectories(directory);
        Files.write(directory.resolve("loopback-"+UUID.randomUUID()+".json"),JSON.writeValueAsBytes(receipts),StandardOpenOption.CREATE_NEW);
    }
    @ParameterizedTest @ValueSource(booleans={true,false})
    void actualCloseOrResetResubscribesAndDuplicatesDoNotFreshenOldData(boolean reset) throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var first=fixture.server.next();fixture.subscriptions(first,true);
            until(()->fixture.state().equals("CONNECTED"));
            first.fragmented(trade("1"));first.text(MarketStreamTest.quote());
            until(()->fixture.hub.snapshot("005930",NOW).state().equals("LIVE"));
            if(reset)first.reset();else first.normalClose();
            var second=fixture.server.next();fixture.subscriptions(second,true);
            until(()->fixture.state().equals("CONNECTED"));
            assertThat(fixture.hub.snapshot("005930",NOW).trade()).isNull();
            second.text(trade("1"));second.text(MarketStreamTest.quote());
            until(()->!fixture.connection.recoverySnapshot().receipts().isEmpty());
            second.text(trade("4"));second.text(MarketStreamTest.quote().replace("100001","100004"));
            until(()->fixture.hub.snapshot("005930",NOW).state().equals("LIVE"));
            until(()->fixture.hub.snapshot("005930",NOW).trade().cumulativeVolume().equals("4"));
            assertThat(fixture.events.values().stream().filter(e->e.type().equals("TRADE")).count()).isEqualTo(2);
            assertThat(fixture.events.values().stream().filter(e->e.type().equals("TRADE")).mapToInt(e->Integer.parseInt(e.volume())).sum()).isEqualTo(2);
            assertThat(fixture.hub.snapshot("005930",NOW).gapDetected()).isTrue();
            assertThat(fixture.connection.recoverySnapshot().receipts()).anyMatch(r->r.state().equals("RECONNECTING"));
            until(()->fixture.connection.recoverySnapshot().receipts().stream().filter(r->r.state().equals("DATA_READY")).count()==2);
            record(reset?"TCP_RESET_RECOVERY":"CLOSE_RECOVERY",fixture);
        }
    }
    @Test void missingQuoteAckTimesOutEvenWhileProtocolPingsAreAnswered() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,false);
            var pings=Executors.newSingleThreadScheduledExecutor();
            try {
                pings.scheduleWithFixedDelay(()->{try {peer.ping();} catch(Exception ignored) {}},0,25,TimeUnit.MILLISECONDS);
                assertThat(peer.frame(10).bytes()).containsExactly(1,2,3);
                fixture.server.next();
                assertThat(fixture.connection.recoverySnapshot().receipts()).anyMatch(r->"SUBSCRIBE_TIMEOUT".equals(r.code()));
                record("ACK_TIMEOUT_WITH_PINGS",fixture);
            } finally {pings.shutdownNow();}
        }
    }
    @Test void silentAcknowledgedSocketRecoversWithoutProcessRestart() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,true);
            fixture.server.next();
            assertThat(fixture.connection.recoverySnapshot().receipts()).anyMatch(r->"HEARTBEAT_TIMEOUT".equals(r.code()));
            record("SILENT_SOCKET_WATCHDOG",fixture);
        }
    }
    @Test void acknowledgedFlappingStopsAtEightFailuresAndDoesNotResetBudget() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();
            for(int i=0;i<8;i++) {
                var peer=fixture.server.next();fixture.subscriptions(peer,true);until(()->fixture.state().equals("CONNECTED"));peer.reset();
            }
            until(()->fixture.state().equals("FAILED"));
            assertThat(fixture.connection.recoverySnapshot().failures()).isEqualTo(8);
            assertThat(fixture.connection.recoverySnapshot().terminal()).isTrue();
            assertThat(fixture.server.noNext(250)).isTrue();assertThat(fixture.server.accepted()).isEqualTo(8);
            record("ACKED_FLAP_BUDGET",fixture);
        }
    }
    @Test void stableFreshFeedsResetRetryBudgetOnlyAfterRecoveryInterval() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var first=fixture.server.next();fixture.subscriptions(first,true);first.reset();
            var second=fixture.server.next();fixture.subscriptions(second,true);until(()->fixture.state().equals("CONNECTED"));
            assertThat(fixture.connection.recoverySnapshot().failures()).isEqualTo(1);
            second.text(trade("1"));second.text(MarketStreamTest.quote());
            until(()->fixture.connection.recoverySnapshot().failures()==0);
            assertThat(fixture.connection.recoverySnapshot().receipts()).anyMatch(r->"RETRY_BUDGET_RESET".equals(r.code()));
            record("STABLE_FRESH_FEED_RESET",fixture);
        }
    }
    @Test void rejectedSubscriptionIsTerminalAndDoesNotEchoRemoteDetails() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var peer=fixture.server.next();peer.frame(1);
            peer.text(ack("H0STCNT0","1").replace("\"rt_cd\":\"1\"","\"rt_cd\":\"1\",\"msg1\":\"private-provider-error\""));
            until(()->fixture.state().equals("FAILED"));
            assertThat(fixture.server.noNext(200)).isTrue();
            assertThat(JSON.writeValueAsString(fixture.connection.recoverySnapshot())).doesNotContain("private-provider-error","synthetic-approval-only","test-only-secret");
            record("REJECTION_TERMINAL",fixture);
        }
    }
    @Test void stopCancelsBackoffAndRetiresCachedDataWithinBound() throws Exception {
        var slow=timing();
        slow=new KisStreamConnection.Timing(slow.idle(),slow.acknowledgement(),slow.connect(),slow.send(),slow.subscriptionInterval(),
            slow.watchdogInterval(),Duration.ofMillis(500),Duration.ofMillis(500),slow.stableReset());
        try(var fixture=new Fixture(slow)) {
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,true);peer.reset();
            until(()->fixture.state().equals("RECONNECTING"));
            long start=System.nanoTime();fixture.connection.stop();
            assertThat(System.nanoTime()-start).isLessThan(TimeUnit.SECONDS.toNanos(1));
            assertThat(fixture.connection.recoverySnapshot().stopped()).isTrue();
            assertThat(fixture.state()).isEqualTo("DISABLED");
            assertThat(fixture.server.noNext(650)).isTrue();
            record("STOP_BACKOFF_BOUND",fixture);
        }
    }
    @Test void retiredSocketCannotPublishACommitThatReturnsAfterWatchdogReconnect() throws Exception {
        try(var fixture=new Fixture()) {
            var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var committed=new CountDownLatch(1);
            doAnswer(call->{
                entered.countDown();if(!release.await(5,TimeUnit.SECONDS))throw new IllegalStateException("TEST_RELEASE_TIMEOUT");
                ((Runnable)call.getArgument(1)).run();committed.countDown();return true;
            }).when(fixture.store).appendCommitted(any(),any());
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,true);peer.text(trade("1"));
            assertThat(entered.await(3,TimeUnit.SECONDS)).isTrue();
            try {
                var replacement=fixture.server.next();fixture.subscriptions(replacement,true);until(()->fixture.state().equals("CONNECTED"));
                release.countDown();assertThat(committed.await(3,TimeUnit.SECONDS)).isTrue();
                assertThat(fixture.hub.snapshot("005930",NOW).trade()).isNull();
                record("RETIRED_COMMIT_SUPPRESSED",fixture);
            } finally {release.countDown();}
        }
    }
    @Test void oldPublicationFailureCannotMarkTheReplacementConnectionFailed() throws Exception {
        var store=mock(MarketStreamStore.class);var journal=mock(MarketAvailabilityJournal.class);
        var callback=new java.util.concurrent.atomic.AtomicReference<Runnable>();
        when(store.minutes(any(),any())).thenReturn(List.of());
        when(store.appendCommitted(any(),any())).thenAnswer(call->{callback.set(call.getArgument(1));return true;});
        doThrow(new IllegalStateException("old journal failure")).when(journal).publish(any(),any());
        var hub=new MarketStreamHub(MarketStreamTest.enabled(),store,journal);
        hub.connection("CONNECTED",null);
        hub.accept(new KisStreamDecoder().decode(trade("1"),NOW).get(0));
        hub.connection("RECONNECTING","CONNECTION_CLOSED");hub.connection("CONNECTED",null);
        assertThatThrownBy(()->callback.get().run()).hasMessage("AVAILABILITY_RECORD_FAILED");
        assertThat(hub.snapshot("005930",NOW).connectionState()).isEqualTo("CONNECTED");
        assertThat(hub.snapshot("005930",NOW).trade()).isNull();
    }
    @Test void blockedMinuteReadDoesNotBlockStopOrReturnRetiredLiveState() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,true);
            until(()->fixture.state().equals("CONNECTED"));
            var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
            doAnswer(call->{entered.countDown();release.await(5,TimeUnit.SECONDS);return List.of();}).when(fixture.store).minutes(any(),any());
            var reader=Executors.newSingleThreadExecutor();
            try {
                var pending=reader.submit(()->fixture.hub.snapshot("005930",NOW.plusSeconds(2)));
                assertThat(entered.await(3,TimeUnit.SECONDS)).isTrue();
                long start=System.nanoTime();fixture.connection.stop();
                assertThat(System.nanoTime()-start).isLessThan(TimeUnit.SECONDS.toNanos(1));
                release.countDown();assertThat(pending.get(3,TimeUnit.SECONDS).state()).isEqualTo("DISABLED");
                record("STOP_DURING_DATABASE_READ",fixture);
            } finally {release.countDown();reader.shutdownNow();}
        }
    }
    @Test void stopDuringUnfinishedRealHandshakeDoesNotReconnectAfterLateRelease() throws Exception {
        try(var fixture=new Fixture(timing(),null,new LoopbackWebSocketServer(true))) {
            fixture.start();assertThat(fixture.server.handshakePending()).isTrue();
            long start=System.nanoTime();fixture.connection.stop();
            assertThat(System.nanoTime()-start).isLessThan(TimeUnit.SECONDS.toNanos(1));
            fixture.server.releaseHandshake();
            Thread.sleep(150); // observe beyond the accelerated reconnect delay
            assertThat(fixture.connection.recoverySnapshot().attempts()).isEqualTo(1);
            assertThat(fixture.state()).isEqualTo("DISABLED");
            assertThat(fixture.connection.recoverySnapshot().receipts()).noneMatch(r->r.state().equals("CONNECTED"));
            record("STOP_PENDING_HANDSHAKE",fixture);
        }
    }
    @Test void providerJsonPingRepliesWithPongAndUnsupportedBinaryStopsPermanently() throws Exception {
        try(var fixture=new Fixture()) {
            fixture.start();var peer=fixture.server.next();fixture.subscriptions(peer,true);
            String ping="{\"header\":{\"tr_id\":\"PINGPONG\"}}";
            peer.text(ping);assertThat(peer.frame(10).text()).isEqualTo(ping);
            peer.send(2,true,new byte[]{1,2,3});
            until(()->fixture.state().equals("FAILED"));
            assertThat(fixture.connection.recoverySnapshot().receipts()).anyMatch(r->"UNSUPPORTED_BINARY_FRAME".equals(r.code()));
            assertThat(fixture.server.noNext(200)).isTrue();
            record("JSON_PING_AND_BINARY_REJECTION",fixture);
        }
    }
    @Test void staleInputsCannotResetFailureBudgetEvenWhenPacketsWereRecentlyReceived() throws Exception {
        var now=new java.util.concurrent.atomic.AtomicReference<>(NOW);
        var clock=new Clock() {
            public ZoneId getZone() {return ZoneOffset.UTC;}
            public Clock withZone(ZoneId zone) {return this;}
            public Instant instant() {return now.get();}
        };
        try(var fixture=new Fixture(timing(),null,new LoopbackWebSocketServer(),clock)) {
            fixture.start();var first=fixture.server.next();fixture.subscriptions(first,true);first.reset();
            var second=fixture.server.next();fixture.subscriptions(second,true);
            second.text(trade("1"));second.text(MarketStreamTest.quote());
            until(()->fixture.hub.snapshot("005930",NOW).state().equals("LIVE"));
            now.set(NOW.plusSeconds(16));
            Thread.sleep(300); // exceeds stableReset, remains below socket inactivity timeout
            assertThat(fixture.hub.snapshot("005930",now.get()).state()).isEqualTo("STALE");
            assertThat(fixture.connection.recoverySnapshot().failures()).isEqualTo(1);
            assertThat(fixture.connection.recoverySnapshot().receipts()).noneMatch(r->"RETRY_BUDGET_RESET".equals(r.code()));
            record("STALE_INPUTS_KEEP_RETRY_BUDGET",fixture);
        }
    }
}
