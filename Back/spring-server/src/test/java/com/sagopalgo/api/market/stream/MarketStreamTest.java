package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.*;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import java.net.*;
import java.net.http.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

class MarketStreamTest {
    static final Instant NOW=Instant.parse("2026-11-03T01:00:05Z");
    static String trade(String time,String price,String quantity,String cumulative) {
        String[] f=new String[47];Arrays.fill(f,"0");f[0]="005930";f[1]=time;f[2]=price;
        f[12]=quantity;f[13]=cumulative;f[33]="20261103";return "0|H0STCNT0|001|"+String.join("^",f);
    }
    static String quote() {
        String[] f=new String[63];Arrays.fill(f,"0");f[0]="005930";f[1]="100001";
        for(int i=0;i<10;i++) {f[3+i]=""+(101+i);f[13+i]=""+(100-i);f[23+i]="2";f[33+i]="3";}
        return "0|H0STASP0|001|"+String.join("^",f);
    }
    static MarketStreamProperties enabled() {return new MarketStreamProperties(true,true,2,"005930",15);}
    final KisStreamDecoder decoder=new KisStreamDecoder();
    @Test void batchedTradesKeepProviderDateAndIntegerPrecision() {
        var one=trade("100001","100.120000","1","100000000000000000001");
        var two=trade("100002","101","2","100000000000000000003");
        var events=decoder.decode("0|H0STCNT0|002|"+one.split("\\|",4)[3]+"^"+two.split("\\|",4)[3],NOW);
        assertThat(events).hasSize(2);assertThat(events.get(0).price()).isEqualTo("100.120000");
        assertThat(events.get(1).cumulativeVolume()).isEqualTo("100000000000000000003");
        assertThat(events.get(0).marketTime()).isEqualTo(Instant.parse("2026-11-03T01:00:01Z"));
        assertThat(events.get(0).dateBasis()).isEqualTo("PROVIDER_DATE");
    }
    @Test void quoteHasTenLevelsAndExplicitlyInferredDate() {
        var value=decoder.decode(quote(),NOW).get(0);
        assertThat(value.asks()).hasSize(10);assertThat(value.bids()).hasSize(10);
        assertThat(value.asks().get(0).price()).isEqualTo("101");
        assertThat(value.bids().get(9).quantity()).isEqualTo("3");
        assertThat(value.dateBasis()).isEqualTo("RECEIVE_DATE_INFERRED");
    }
    @ParameterizedTest @ValueSource(strings={"1|H0STCNT0|001|secret","0|H0STCNI0|001|secret","0|H0STCNT0|000|", "0|H0STCNT0|101|x","0|H0STASP0|001|x"})
    void unsupportedOrEncryptedFramesFailWithoutEcho(String value) {
        assertThatThrownBy(()->decoder.decode(value,NOW)).isInstanceOf(IllegalArgumentException.class).hasMessage("INVALID_KIS_PUBLIC_STREAM");
    }
    @Test void malformedTimeDateAndNumbersFailClosed() {
        for(String value:List.of(trade("100060","100","1","2"),trade("100100","100","1","2"),
            trade("100001","-100","1","2"),trade("100001","100","1.1","2"),
            trade("100001","100","3","2"),trade("100001","100","1","2").replace("20261103","20260230")))
            assertThatThrownBy(()->decoder.decode(value,NOW)).isInstanceOf(RuntimeException.class);
    }
    @Test void lateTradesProduceDeterministicOpenCloseAndVolume() {
        var last=decoder.decode(trade("100003","103","2","5"),NOW).get(0);
        var first=decoder.decode(trade("100001","101","1","1"),NOW).get(0);
        var middle=decoder.decode(trade("100003","102","2","3"),NOW).get(0);
        var bar=StreamMinuteBar.first(last).add(first).add(middle);
        assertThat(bar.open()).isEqualTo("101");assertThat(bar.close()).isEqualTo("103");
        assertThat(bar.high()).isEqualTo("103");assertThat(bar.low()).isEqualTo("101");
        assertThat(bar.volume()).isEqualTo("5");assertThat(bar.coverage()).isEqualTo("OBSERVED_ONLY");
    }
    @Test void liveRequiresAcknowledgedConnectionAndBothFreshDataTypes() {
        var store=mock(MarketStreamStore.class);when(store.append(any())).thenReturn(true);when(store.minutes(any(),any())).thenReturn(List.of());
        var hub=new MarketStreamHub(enabled(),store);hub.connection("SUBSCRIBING",null);
        hub.accept(decoder.decode(trade("100001","100","1","1"),NOW).get(0));hub.accept(decoder.decode(quote(),NOW).get(0));
        assertThat(hub.snapshot("005930",NOW).state()).isEqualTo("SUBSCRIBING");
        hub.connection("CONNECTED",null);assertThat(hub.snapshot("005930",NOW).state()).isEqualTo("LIVE");
        assertThat(hub.snapshot("005930",NOW.plusSeconds(16)).state()).isEqualTo("STALE");
        hub.connection("RECONNECTING","CONNECTION_CLOSED");
        assertThat(hub.snapshot("005930",NOW).trade()).isNull();
        hub.connection("CONNECTED",null);assertThat(hub.snapshot("005930",NOW).state()).isEqualTo("WAITING_DATA");
    }
    @Test void duplicateAndOutOfOrderTicksDoNotFreshenOrRegressLatestTrade() {
        var store=mock(MarketStreamStore.class);when(store.append(any())).thenReturn(true);when(store.minutes(any(),any())).thenReturn(List.of());
        var hub=new MarketStreamHub(enabled(),store);hub.connection("CONNECTED",null);
        hub.accept(decoder.decode(trade("100003","103","1","3"),NOW).get(0));
        hub.accept(decoder.decode(trade("100001","101","1","1"),NOW).get(0));hub.accept(decoder.decode(quote(),NOW).get(0));
        assertThat(hub.snapshot("005930",NOW).trade().price()).isEqualTo("103");
        when(store.append(any())).thenReturn(false);
        hub.accept(decoder.decode(trade("100003","103","1","3"),NOW.plusSeconds(20)).get(0));
        assertThat(hub.snapshot("005930",NOW.plusSeconds(20)).state()).isEqualTo("STALE");
        assertThatThrownBy(()->hub.accept(new MarketStreamEvent("id","000660","TRADE",NOW,NOW,"1","1","1",List.of(),List.of(),"0","PROVIDER_DATE")))
            .isInstanceOf(IllegalArgumentException.class);
    }
    @Test void defaultOffReadsNoStorageAndOpensNoProviderConnection() {
        var policy=new MarketStreamProperties(false,false,0,"",15);var store=mock(MarketStreamStore.class);
        var hub=new MarketStreamHub(policy,store);
        assertThat(hub.snapshot("005930",NOW).state()).isEqualTo("DISABLED");verifyNoInteractions(store);
        var rest=mock(RestClient.class);var http=mock(HttpClient.class);
        var connection=new KisStreamConnection(new KisMarketProperties(),policy,hub,rest,new ObjectMapper(),http);
        connection.start();connection.stop();verifyNoInteractions(rest,http,store);
    }
    @Test void missingStoragePreventsApprovalBeforeConnecting() {
        var hub=mock(MarketStreamHub.class);doThrow(new IllegalStateException()).when(hub).verifyStorage();
        var rest=mock(RestClient.class);var http=mock(HttpClient.class);
        var c=new KisStreamConnection(new KisMarketProperties(),enabled(),hub,rest,new ObjectMapper(),http);
        c.start();c.stop();verify(hub).connection("FAILED","STORAGE_025_REQUIRED");verifyNoInteractions(rest,http);
    }
    @Test void subscriptionsArePublicOnlyAndAcknowledgementsGateData() throws Exception {
        var kis=new KisMarketProperties();kis.setEnabled(true);kis.setAppKey("test-key");kis.setAppSecret("test-secret");
        var builder=RestClient.builder();var server=MockRestServiceServer.bindTo(builder).build();
        server.expect(requestTo("https://openapi.koreainvestment.com:9443/oauth2/Approval"))
            .andExpect(org.springframework.test.web.client.match.MockRestRequestMatchers.content().json("{\"grant_type\":\"client_credentials\",\"appkey\":\"test-key\",\"secretkey\":\"test-secret\"}"))
            .andRespond(withSuccess("{\"approval_key\":\"private-approval\"}",MediaType.APPLICATION_JSON));
        var http=mock(HttpClient.class);var wsBuilder=mock(WebSocket.Builder.class);var ws=mock(WebSocket.class);
        when(http.newWebSocketBuilder()).thenReturn(wsBuilder);when(wsBuilder.connectTimeout(any())).thenReturn(wsBuilder);
        when(ws.sendText(any(),eq(true))).thenReturn(CompletableFuture.completedFuture(ws));
        var listener=new AtomicReference<WebSocket.Listener>();var ready=new CountDownLatch(1);
        when(wsBuilder.buildAsync(any(),any())).thenAnswer(call->{listener.set(call.getArgument(1));listener.get().onOpen(ws);ready.countDown();return CompletableFuture.completedFuture(ws);});
        var hub=mock(MarketStreamHub.class);var connection=new KisStreamConnection(kis,enabled(),hub,builder.build(),new ObjectMapper(),http);
        try {
            connection.start();assertThat(ready.await(5,TimeUnit.SECONDS)).isTrue();
            verify(ws,timeout(4000).times(2)).sendText(any(),eq(true));
            for(String tr:List.of("H0STCNT0","H0STASP0")) listener.get().onText(ws,"{\"header\":{\"tr_id\":\""+tr+"\",\"tr_key\":\"005930\"},\"body\":{\"rt_cd\":\"0\"}}",true);
            verify(hub).connection("CONNECTED",null);
            listener.get().onText(ws,"{\"header\":{\"tr_id\":\"H0STCNT0\",\"tr_key\":\"005930\"},\"body\":{\"rt_cd\":\"1\",\"msg1\":\"private-error\"}}",true);
            verify(hub).connection("FAILED","SUBSCRIPTION_REJECTED");server.verify();
        } finally {connection.stop();}
    }
    @Test void configurationRejectsUnapprovedBudgetAndMalformedSymbols() {
        assertThatThrownBy(()->new MarketStreamProperties(true,false,2,"005930",15)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->new MarketStreamProperties(true,true,1,"005930",15)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->new MarketStreamProperties(true,true,4,"005930,005930",15)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->new MarketStreamProperties(false,false,0,"005930,",15)).isInstanceOf(IllegalArgumentException.class);
    }
    @Test void statusHttpIsNoStoreAndNeverQueriesProvider() throws Exception {
        var store=mock(MarketStreamStore.class);var hub=new MarketStreamHub(new MarketStreamProperties(false,false,0,"",15),store);
        var controller=new MarketStreamController(hub);
        try {
            var mvc=MockMvcBuilders.standaloneSetup(controller).setControllerAdvice(new GlobalExceptionHandler()).build();
            mvc.perform(get("/api/v1/market/realtime").param("stockCode","005930"))
                .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
                .andExpect(jsonPath("$.data.state").value("DISABLED")).andExpect(jsonPath("$.data.usableForTrading").value(false));
            mvc.perform(get("/api/v1/market/realtime").param("stockCode","../bad")).andExpect(status().isBadRequest());
            verifyNoInteractions(store);
        } finally {controller.stop();}
    }
}
