package com.sagopalgo.api.market.stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.MarketStreamProperties;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.net.URI;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

/** 공개 시세 전용 단일 서버 연결. 승인키/프레임/외부 오류 원문을 로그에 남기지 않습니다. */
@Component
public class KisStreamConnection {
    private final KisMarketProperties kis;
    private final MarketStreamProperties policy;
    private final MarketStreamHub hub;
    private final RestClient rest;
    private final ObjectMapper json;
    private final HttpClient http;
    private final KisStreamDecoder decoder=new KisStreamDecoder();
    private final ScheduledExecutorService worker=Executors.newSingleThreadScheduledExecutor(r -> {var t=new Thread(r,"kis-public-stream");t.setDaemon(true);return t;});
    private volatile WebSocket socket;
    private volatile boolean stopped=false,hardFailure=false;
    private volatile long generation=0;
    private volatile Instant lastActivity=Instant.EPOCH;
    private volatile Instant subscriptionStarted=Instant.EPOCH;
    private volatile boolean awaitingAcknowledgement=false;
    private int failures=0;
    private String approval;
    private Instant approvalUntil=Instant.EPOCH;
    @org.springframework.beans.factory.annotation.Autowired
    public KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json) {
        this(kis,policy,hub,rest,json,HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build());
    }
    KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json,HttpClient http) {
        this.kis=kis;this.policy=policy;this.hub=hub;this.rest=rest;this.json=json;this.http=http;
    }
    @PostConstruct void start() {
        if(!policy.enabled()) return;
        try {hub.verifyStorage();} catch(RuntimeException e) {hub.connection("FAILED","STORAGE_025_REQUIRED");return;}
        if(!kis.isEnabled() || kis.getAppKey().isBlank() || kis.getAppSecret().isBlank() ||
            !"https://openapi.koreainvestment.com:9443".equals(kis.getBaseUrl().replaceAll("/+$",""))) {
            hub.connection("FAILED","CONFIGURATION_REQUIRED");return;
        }
        worker.execute(this::connect);
        worker.scheduleWithFixedDelay(() -> {
            if(socket!=null && Instant.now().isAfter(lastActivity.plusSeconds(60))) failed(generation,"HEARTBEAT_TIMEOUT",false);
            else if(socket!=null && awaitingAcknowledgement && Instant.now().isAfter(subscriptionStarted.plusSeconds(60))) failed(generation,"SUBSCRIBE_TIMEOUT",false);
        },10,10,TimeUnit.SECONDS);
    }
    private void connect() {
        if(stopped || hardFailure) return;
        long epoch=++generation;
        hub.connection("CONNECTING",null);
        try {
            String key=approval();
            var listener=new Listener(epoch,key);
            WebSocket ws=http.newWebSocketBuilder().connectTimeout(Duration.ofSeconds(10))
                .buildAsync(URI.create("ws://ops.koreainvestment.com:21000/tryitout"),listener).get(15,TimeUnit.SECONDS);
            if(stopped || epoch!=generation) ws.abort(); else socket=ws;
        } catch(Exception e) {failed(epoch,"CONNECTION_FAILED",false);}
    }
    private synchronized String approval() {
        if(approval!=null && Instant.now().isBefore(approvalUntil)) return approval;
        var body=rest.post().uri(kis.getBaseUrl().replaceAll("/+$","")+"/oauth2/Approval")
            .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
            .body(Map.of("grant_type","client_credentials","appkey",kis.getAppKey(),"secretkey",kis.getAppSecret()))
            .retrieve().body(com.fasterxml.jackson.databind.JsonNode.class);
        if(body==null || !body.path("approval_key").isTextual() || body.path("approval_key").asText().isBlank())
            throw new IllegalStateException("APPROVAL_FAILED");
        approval=body.path("approval_key").asText();approvalUntil=Instant.now().plusSeconds(23*3600);return approval;
    }
    private synchronized void failed(long epoch,String code,boolean fatal) {
        if(stopped || epoch!=generation) return;
        generation++;
        WebSocket old=socket;socket=null;if(old!=null) old.abort();
        hardFailure=fatal;
        failures++;
        if(fatal || failures>=8) {hub.connection("FAILED",code);return;}
        hub.connection("RECONNECTING",code);
        worker.schedule(this::connect,Math.min(60,5L << Math.min(failures-1,4)),TimeUnit.SECONDS);
    }
    private class Listener implements WebSocket.Listener {
        private final long epoch;
        private final String key;
        private final StringBuilder fragments=new StringBuilder();
        private final Set<String> acknowledgements=new HashSet<>();
        Listener(long epoch,String key) {this.epoch=epoch;this.key=key;}
        public void onOpen(WebSocket ws) {
            if(stopped || epoch!=generation) {ws.abort();return;}
            socket=ws;lastActivity=Instant.now();subscriptionStarted=lastActivity;awaitingAcknowledgement=true;hub.connection("SUBSCRIBING",null);
            // 하나씩 전송해 공급자 요청 순서를 유지하며 무한 요청 큐를 만들지 않습니다.
            worker.execute(() -> {
                try {
                    for(String stock:policy.stockCodes()) for(String tr:List.of("H0STCNT0","H0STASP0")) {
                        if(stopped || epoch!=generation) return;
                        ws.sendText(subscription(key,tr,stock),true).get(10,TimeUnit.SECONDS);
                        Thread.sleep(1000);
                    }
                } catch(Exception e) {failed(epoch,"SUBSCRIBE_FAILED",false);}
            });
            ws.request(1);
        }
        public CompletionStage<?> onText(WebSocket ws,CharSequence part,boolean last) {
            if(stopped || epoch!=generation) return null;
            lastActivity=Instant.now();
            if(fragments.length()+part.length()>262144) {failed(epoch,"FRAME_LIMIT",true);return null;}
            fragments.append(part);
            if(last) {
                String frame=fragments.toString();fragments.setLength(0);
                try {
                    if(frame.startsWith("{")) {
                        var message=json.readTree(frame);String tr=message.path("header").path("tr_id").asText();
                        if("PINGPONG".equals(tr)) {
                            byte[] ping=frame.getBytes(StandardCharsets.UTF_8);
                            if(ping.length>125) throw new IllegalArgumentException();
                            ws.sendPong(ByteBuffer.wrap(ping));
                        } else {
                            String stock=message.path("header").path("tr_key").asText();
                            if(!policy.stockCodes().contains(stock) || !List.of("H0STCNT0","H0STASP0").contains(tr) ||
                                !"0".equals(message.path("body").path("rt_cd").asText())) {
                                failed(epoch,"SUBSCRIPTION_REJECTED",true);return null;
                            }
                            acknowledgements.add(tr+stock);
                            if(acknowledgements.size()==policy.stockCodes().size()*2) {
                                failures=0;awaitingAcknowledgement=false;hub.connection("CONNECTED",null);
                            }
                        }
                    } else {
                        for(var event:decoder.decode(frame,Instant.now())) {
                            if(!acknowledgements.contains(("TRADE".equals(event.type())?"H0STCNT0":"H0STASP0")+event.stockCode()))
                                throw new IllegalArgumentException();
                            hub.accept(event);
                        }
                    }
                } catch(IllegalArgumentException e) {failed(epoch,"INVALID_FRAME",true);return null;}
                catch(Exception e) {failed(epoch,"STORAGE_OR_PROTOCOL_FAILURE",true);return null;}
            }
            ws.request(1);return null;
        }
        public CompletionStage<?> onClose(WebSocket ws,int code,String reason) {failed(epoch,"CONNECTION_CLOSED",false);return null;}
        public CompletionStage<?> onPing(WebSocket ws,ByteBuffer message) {if(epoch==generation) lastActivity=Instant.now();ws.request(1);return null;}
        public CompletionStage<?> onPong(WebSocket ws,ByteBuffer message) {if(epoch==generation) lastActivity=Instant.now();ws.request(1);return null;}
        public void onError(WebSocket ws,Throwable error) {failed(epoch,"CONNECTION_FAILED",false);}
    }
    String subscription(String approval,String tr,String stock) {
        try {return json.writeValueAsString(Map.of("header",Map.of("approval_key",approval,"custtype","P","tr_type","1","content-type","utf-8"),
            "body",Map.of("input",Map.of("tr_id",tr,"tr_key",stock))));}
        catch(Exception e) {throw new IllegalStateException("SUBSCRIBE_FAILED");}
    }
    @PreDestroy void stop() {stopped=true;generation++;var ws=socket;if(ws!=null) ws.abort();worker.shutdownNow();}
}
