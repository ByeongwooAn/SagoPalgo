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

/** Public market data only. Lifecycle receipts never contain credentials or frames. */
@Component
public class KisStreamConnection {
    static final URI ENDPOINT=URI.create("ws://ops.koreainvestment.com:21000/tryitout");
    private static final List<String> TRS=List.of("H0STCNT0","H0STASP0");
    record Timing(Duration idle,Duration acknowledgement,Duration connect,Duration send,
                  Duration subscriptionInterval,Duration watchdogInterval,Duration backoffBase,
                  Duration backoffMaximum,Duration stableReset) {
        Timing {
            for(var duration:List.of(idle,acknowledgement,connect,send,subscriptionInterval,watchdogInterval,backoffBase,backoffMaximum,stableReset))
                if(duration.isNegative() || duration.isZero() || duration.toMillis()<1 || duration.compareTo(Duration.ofDays(1))>0)
                    throw new IllegalArgumentException("INVALID_STREAM_TIMING");
            if(backoffBase.compareTo(backoffMaximum)>0)throw new IllegalArgumentException("INVALID_STREAM_TIMING");
        }
        static Timing production() {return new Timing(Duration.ofSeconds(60),Duration.ofSeconds(60),Duration.ofSeconds(15),
            Duration.ofSeconds(10),Duration.ofSeconds(1),Duration.ofSeconds(10),Duration.ofSeconds(5),Duration.ofSeconds(60),Duration.ofSeconds(60));}
    }
    record Receipt(long sequence,long generation,String state,String code,Instant observedAt,long elapsedNanos) {}
    record RecoverySnapshot(String clockDomain,boolean utcSynchronized,boolean stopped,boolean terminal,
                            int attempts,int failures,List<Receipt> receipts,StreamOperationsJournal.Status journal,StreamOperationsJournal.Counters counters) {}
    private final KisMarketProperties kis;
    private final MarketStreamProperties policy;
    private final MarketStreamHub hub;
    private final RestClient rest;
    private final ObjectMapper json;
    private final HttpClient http;
    private final URI endpoint;
    private final Timing timing;
    private final Clock clock;
    private final StreamOperationsJournal journal;
    private final KisStreamDecoder decoder=new KisStreamDecoder();
    private final ScheduledExecutorService worker=Executors.newSingleThreadScheduledExecutor(r -> daemon(r,"kis-public-control"));
    private final ExecutorService connector=Executors.newSingleThreadExecutor(r -> daemon(r,"kis-public-connect"));
    private final Object approvalLock=new Object();
    private final ArrayDeque<Receipt> receipts=new ArrayDeque<>();
    private final String clockDomain=UUID.randomUUID().toString();
    private final long origin=System.nanoTime();
    private WebSocket socket;
    private CompletableFuture<WebSocket> opening,sending;
    private Future<?> approvalTask;
    private ScheduledFuture<?> retryTask;
    private boolean stopped,hardFailure,started,connecting;
    private long generation,activityNanos,attemptNanos;
    private int failures,attempts;
    private long receiptSequence;
    private long receivedPublicFrames,decodedEvents,storageInsertions,nonInsertions,storageFailures,retiredCompletions,inFlightStorage;
    private StreamOperationsJournal.Counters checkpoint=StreamOperationsJournal.Counters.zero();
    private Listener current;
    private String approval;
    private Instant approvalUntil=Instant.EPOCH;

    public KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json) {
        this(kis,policy,hub,rest,json,HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build());
    }
    @org.springframework.beans.factory.annotation.Autowired
    public KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json,StreamOperationsJournal journal) {
        this(kis,policy,hub,rest,json,HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build(),ENDPOINT,Timing.production(),Clock.systemUTC(),journal);
    }
    KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json,HttpClient http) {
        this(kis,policy,hub,rest,json,http,ENDPOINT,Timing.production(),Clock.systemUTC());
    }
    // Package-only test seam; no environment/property can redirect the production endpoint or timings.
    KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json,
                        HttpClient http,URI endpoint,Timing timing,Clock clock) {
        this(kis,policy,hub,rest,json,http,endpoint,timing,clock,StreamOperationsJournal.disabled());
    }
    KisStreamConnection(KisMarketProperties kis,MarketStreamProperties policy,MarketStreamHub hub,RestClient rest,ObjectMapper json,
                        HttpClient http,URI endpoint,Timing timing,Clock clock,StreamOperationsJournal journal) {
        this.kis=kis;this.policy=policy;this.hub=hub;this.rest=rest;this.json=json;this.http=http;
        this.endpoint=endpoint;this.timing=timing;this.clock=clock;this.journal=journal;
    }
    private static Thread daemon(Runnable task,String name) {var thread=new Thread(task,name);thread.setDaemon(true);return thread;}
    private boolean active(long epoch) {return !stopped && !hardFailure && epoch==generation && journal.healthy();}
    private void state(String state,String code) {
        hub.connection(state,code);
        recordReceipt(state,code);
    }
    private void recordReceipt(String state,String code) {
        if(receipts.size()==128)receipts.removeFirst();
        receipts.addLast(new Receipt(++receiptSequence,generation,state,code,clock.instant(),System.nanoTime()-origin));
        journal.append(StreamOperationsJournal.Kind.LIFECYCLE,operation(state,code));
    }
    private StreamOperationsJournal.Counters counters() {
        return new StreamOperationsJournal.Counters(receivedPublicFrames,decodedEvents,storageInsertions,nonInsertions,storageFailures,retiredCompletions,inFlightStorage);
    }
    private StreamOperationsJournal.Operation operation(String state,String code) {
        return new StreamOperationsJournal.Operation(receiptSequence,generation,state,code,clock.instant().toString(),System.nanoTime()-origin,counters());
    }
    private void journalFailed(String code) {
        try {worker.execute(this::stopForJournalFailure);} catch(RejectedExecutionException ignored) {}
    }
    private synchronized void stopForJournalFailure() {
        if(stopped || hardFailure)return;
        generation++;hardFailure=true;connecting=false;state("FAILED","OPERATIONS_JOURNAL_FAILED");cancelPending();
        var ws=socket;socket=null;current=null;if(ws!=null)ws.abort();
    }
    synchronized RecoverySnapshot recoverySnapshot() {
        return new RecoverySnapshot(clockDomain,false,stopped,hardFailure,attempts,failures,List.copyOf(receipts),journal.status(),counters());
    }
    @PostConstruct void start() {
        synchronized(this) {if(started || stopped)return;started=true;}
        if(!policy.enabled())return;
        try {
            StreamOperationsJournal.Operation initial;
            synchronized(this) {if(stopped)return;initial=operation("SESSION_START",null);}
            journal.start(UUID.fromString(clockDomain),initial,this::journalFailed);
        } catch(RuntimeException error) {
            synchronized(this) {if(!stopped) {hardFailure=true;state("FAILED","OPERATIONS_JOURNAL_REQUIRED");}}return;
        }
        synchronized(this) {if(stopped)return;}
        try {hub.verifyStorage();} catch(RuntimeException e) {synchronized(this) {if(!stopped) {hardFailure=true;state("FAILED","STORAGE_025_REQUIRED");}}return;}
        synchronized(this) {
            if(stopped)return;
            if(!kis.isEnabled() || kis.getAppKey().isBlank() || kis.getAppSecret().isBlank() ||
                !"https://openapi.koreainvestment.com:9443".equals(kis.getBaseUrl().replaceAll("/+$",""))) {
                hardFailure=true;state("FAILED","CONFIGURATION_REQUIRED");return;
            }
            worker.execute(this::connect);
            worker.scheduleWithFixedDelay(this::checkHealth,timing.watchdogInterval().toMillis(),timing.watchdogInterval().toMillis(),TimeUnit.MILLISECONDS);
        }
    }
    private void connect() {
        final long epoch;
        synchronized(this) {
            if(stopped || hardFailure || connecting || socket!=null)return;
            epoch=++generation;attempts++;connecting=true;attemptNanos=System.nanoTime();state("CONNECTING",null);
            approvalTask=connector.submit(()->open(epoch));
        }
    }
    private void open(long epoch) {
        try {
            synchronized(this) {if(!active(epoch))return;}
            String key=approval();
            synchronized(this) {
                if(!active(epoch))return;
                var listener=new Listener(epoch,key);
                current=listener;
                opening=http.newWebSocketBuilder().connectTimeout(timing.connect()).buildAsync(endpoint,listener);
                opening.orTimeout(timing.connect().toMillis(),TimeUnit.MILLISECONDS).whenComplete((ws,error)->{
                    if(error!=null)failed(epoch,"CONNECTION_FAILED",false);
                    else {synchronized(KisStreamConnection.this) {if(!active(epoch))ws.abort();}}
                });
            }
        } catch(Exception e) {failed(epoch,"CONNECTION_FAILED",false);}
    }
    private String approval() {
        synchronized(approvalLock) {
            if(approval!=null && clock.instant().isBefore(approvalUntil))return approval;
            var body=rest.post().uri(kis.getBaseUrl().replaceAll("/+$","")+"/oauth2/Approval")
                .contentType(org.springframework.http.MediaType.APPLICATION_JSON)
                .body(Map.of("grant_type","client_credentials","appkey",kis.getAppKey(),"secretkey",kis.getAppSecret()))
                .retrieve().body(com.fasterxml.jackson.databind.JsonNode.class);
            if(body==null || !body.path("approval_key").isTextual() || body.path("approval_key").asText().isBlank())
                throw new IllegalStateException("APPROVAL_FAILED");
            approval=body.path("approval_key").asText();approvalUntil=clock.instant().plusSeconds(23*3600);return approval;
        }
    }
    private synchronized void checkHealth() {
        if(stopped || hardFailure)return;
        if(!journal.healthy()) {stopForJournalFailure();return;}
        var snapshot=counters();
        if(!snapshot.equals(checkpoint)) {journal.append(StreamOperationsJournal.Kind.COUNTERS,operation("COUNTERS",null));checkpoint=snapshot;}
        long now=System.nanoTime();
        if(connecting && now-attemptNanos>=timing.connect().toNanos()) {failed(generation,"CONNECT_TIMEOUT",false);return;}
        if(socket==null || current==null)return;
        // Subscription timeout is independent of ping traffic, including healthy control frames.
        if(current.awaiting && now-current.openedNanos>=timing.acknowledgement().toNanos()) {failed(generation,"SUBSCRIBE_TIMEOUT",false);return;}
        if(now-activityNanos>=timing.idle().toNanos()) {failed(generation,"HEARTBEAT_TIMEOUT",false);return;}
        if(!current.awaiting && now-current.acknowledgedNanos>=timing.stableReset().toNanos() &&
            current.dataAt.size()==policy.stockCodes().size()*2 && current.dataAt.values().stream().allMatch(at->now-at<Duration.ofSeconds(policy.staleSeconds()).toNanos()) &&
            hub.freshInputs(clock.instant())) {
            if(failures>0) {failures=0;recordReceipt("STABLE","RETRY_BUDGET_RESET");}
        }
    }
    private synchronized void failed(long epoch,String code,boolean fatal) {
        if(!active(epoch))return;
        generation++;connecting=false;failures++;
        hardFailure=fatal || failures>=8;
        // Retire the publication generation before closing a socket or cancelling its futures.
        state(hardFailure?"FAILED":"RECONNECTING",code);
        cancelPending();
        WebSocket old=socket;socket=null;current=null;if(old!=null)old.abort();
        if(!hardFailure) {
            long token=generation;
            long delay=Math.min(timing.backoffMaximum().toMillis(),timing.backoffBase().toMillis()*(1L<<Math.min(failures-1,4)));
            retryTask=worker.schedule(()->{synchronized(KisStreamConnection.this) {if(!active(token))return;connect();}},delay,TimeUnit.MILLISECONDS);
        }
    }
    private void cancelPending() {
        if(retryTask!=null)retryTask.cancel(false);
        if(approvalTask!=null)approvalTask.cancel(true);
        if(opening!=null && !opening.isDone())opening.cancel(true);
        if(sending!=null && !sending.isDone())sending.cancel(true);
    }
    private class Listener implements WebSocket.Listener {
        private final long epoch;
        private final String key;
        private final StringBuilder fragments=new StringBuilder();
        private final Set<String> sent=new HashSet<>(),acknowledgements=new HashSet<>();
        private final Map<String,Long> dataAt=new HashMap<>();
        private long openedNanos,acknowledgedNanos,publicationGeneration;
        private boolean awaiting=true,dataReady;
        Listener(long epoch,String key) {this.epoch=epoch;this.key=key;}
        public void onOpen(WebSocket ws) {
            synchronized(KisStreamConnection.this) {
                if(!active(epoch)) {ws.abort();return;}
                socket=ws;connecting=false;openedNanos=activityNanos=System.nanoTime();state("SUBSCRIBING",null);
                publicationGeneration=hub.generation();
                worker.execute(()->subscribe(ws,0));
                ws.request(1);
            }
        }
        private void subscribe(WebSocket ws,int index) {
            if(index>=policy.stockCodes().size()*2)return;
            String stock=policy.stockCodes().get(index/2),tr=TRS.get(index%2);
            synchronized(KisStreamConnection.this) {
                if(!active(epoch) || socket!=ws)return;
                try {
                    sent.add(tr+stock);
                    sending=ws.sendText(subscription(key,tr,stock),true);
                    sending.orTimeout(timing.send().toMillis(),TimeUnit.MILLISECONDS).whenComplete((ignored,error)->{
                        synchronized(KisStreamConnection.this) {
                            if(!active(epoch))return;
                            if(error!=null) {failed(epoch,"SUBSCRIBE_FAILED",false);return;}
                            worker.schedule(()->subscribe(ws,index+1),timing.subscriptionInterval().toMillis(),TimeUnit.MILLISECONDS);
                        }
                    });
                } catch(Exception error) {failed(epoch,"SUBSCRIBE_FAILED",false);}
            }
        }
        public CompletionStage<?> onText(WebSocket ws,CharSequence part,boolean last) {
            synchronized(KisStreamConnection.this) {if(!active(epoch))return null;activityNanos=System.nanoTime();}
            if(fragments.length()+part.length()>262144) {failed(epoch,"FRAME_LIMIT",true);return null;}
            fragments.append(part);
            if(last) {
                String frame=fragments.toString();fragments.setLength(0);
                try {
                    if(frame.startsWith("{")) {
                        var message=json.readTree(frame);String tr=message.path("header").path("tr_id").asText();
                        synchronized(KisStreamConnection.this) {
                            if(!active(epoch))return null;
                            if("PINGPONG".equals(tr)) {
                                byte[] ping=frame.getBytes(StandardCharsets.UTF_8);
                                if(ping.length>125)throw new IllegalArgumentException();
                                ws.sendPong(ByteBuffer.wrap(ping)).whenComplete((ignored,error)->{if(error!=null)failed(epoch,"PONG_FAILED",false);});
                            } else {
                                String stock=message.path("header").path("tr_key").asText();
                                if(!sent.contains(tr+stock) || !"0".equals(message.path("body").path("rt_cd").asText())) {
                                    failed(epoch,"SUBSCRIPTION_REJECTED",true);return null;
                                }
                                acknowledgements.add(tr+stock);
                                if(awaiting && acknowledgements.size()==policy.stockCodes().size()*2) {
                                    awaiting=false;acknowledgedNanos=System.nanoTime();state("CONNECTED",null);
                                }
                            }
                        }
                    } else {
                        synchronized(KisStreamConnection.this) {if(!active(epoch))return null;receivedPublicFrames++;}
                        var decoded=decoder.decode(frame,clock.instant());
                        synchronized(KisStreamConnection.this) {if(!active(epoch))return null;decodedEvents+=decoded.size();}
                        for(var event:decoded) {
                            String tr="TRADE".equals(event.type())?"H0STCNT0":"H0STASP0";
                            synchronized(KisStreamConnection.this) {
                                if(!active(epoch))return null;
                                if(!acknowledgements.contains(tr+event.stockCode()))throw new IllegalArgumentException();
                                inFlightStorage++;
                            }
                            boolean added;
                            try {added=hub.accept(event,publicationGeneration);}
                            catch(RuntimeException error) {
                                synchronized(KisStreamConnection.this) {inFlightStorage--;if(!stopped) {storageFailures++;if(epoch!=generation)retiredCompletions++;}}
                                throw error;
                            }
                            synchronized(KisStreamConnection.this) {
                                inFlightStorage--;
                                if(!stopped) {if(added)storageInsertions++;else nonInsertions++;if(epoch!=generation)retiredCompletions++;}
                                if(active(epoch) && added && !event.marketTime().isBefore(clock.instant().minusSeconds(policy.staleSeconds())))
                                    dataAt.put(tr+event.stockCode(),System.nanoTime());
                                if(active(epoch) && !dataReady && dataAt.size()==policy.stockCodes().size()*2) {
                                    dataReady=true;recordReceipt("DATA_READY",null);
                                }
                            }
                        }
                    }
                } catch(IllegalArgumentException e) {failed(epoch,"INVALID_FRAME",true);return null;}
                catch(Exception e) {failed(epoch,"STORAGE_OR_PROTOCOL_FAILURE",true);return null;}
            }
            synchronized(KisStreamConnection.this) {if(active(epoch))ws.request(1);}
            return null;
        }
        public CompletionStage<?> onClose(WebSocket ws,int code,String reason) {failed(epoch,"CONNECTION_CLOSED",false);return null;}
        public CompletionStage<?> onPing(WebSocket ws,ByteBuffer message) {return activity(ws);}
        public CompletionStage<?> onPong(WebSocket ws,ByteBuffer message) {return activity(ws);}
        private CompletionStage<?> activity(WebSocket ws) {
            synchronized(KisStreamConnection.this) {if(active(epoch)) {activityNanos=System.nanoTime();ws.request(1);}}
            return null; // JDK WebSocket automatically replies to protocol Ping with Pong.
        }
        public CompletionStage<?> onBinary(WebSocket ws,ByteBuffer bytes,boolean last) {failed(epoch,"UNSUPPORTED_BINARY_FRAME",true);return null;}
        public void onError(WebSocket ws,Throwable error) {failed(epoch,"CONNECTION_FAILED",false);}
    }
    String subscription(String approval,String tr,String stock) {
        try {return json.writeValueAsString(Map.of("header",Map.of("approval_key",approval,"custtype","P","tr_type","1","content-type","utf-8"),
            "body",Map.of("input",Map.of("tr_id",tr,"tr_key",stock))));}
        catch(Exception e) {throw new IllegalStateException("SUBSCRIBE_FAILED");}
    }
    @PreDestroy void stop() {
        StreamOperationsJournal.Operation terminal;
        synchronized(this) {
        if(stopped)return;
        stopped=true;generation++;connecting=false;state("DISABLED","COLLECTOR_STOPPED");cancelPending();
        var ws=socket;socket=null;current=null;if(ws!=null)ws.abort();worker.shutdownNow();connector.shutdownNow();
        terminal=operation("SESSION_END",null);
        }
        journal.finish(terminal);
    }
}
