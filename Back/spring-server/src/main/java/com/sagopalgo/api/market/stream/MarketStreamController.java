package com.sagopalgo.api.market.stream;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.response.ApiResponse;
import jakarta.annotation.PreDestroy;
import java.time.Instant;
import java.util.concurrent.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/v1/market/realtime")
public class MarketStreamController {
    private final MarketStreamHub hub;
    private final java.util.Map<SseEmitter,String> clients=new ConcurrentHashMap<>();
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor(r -> {var t=new Thread(r,"market-sse-timer");t.setDaemon(true);return t;});
    private final ThreadPoolExecutor sender=new ThreadPoolExecutor(2,2,0,TimeUnit.SECONDS,new ArrayBlockingQueue<>(20),r -> {var t=new Thread(r,"market-sse-send");t.setDaemon(true);return t;});
    private final java.util.Set<SseEmitter> sending=ConcurrentHashMap.newKeySet();
    public MarketStreamController(MarketStreamHub hub) {this.hub=hub;timer.scheduleWithFixedDelay(this::publish,1,1,TimeUnit.SECONDS);}
    @GetMapping public ResponseEntity<?> snapshot(@RequestParam String stockCode) {
        validate(stockCode);
        try {return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(hub.snapshot(stockCode,Instant.now()),"KRX 공개 시세 관측 상태입니다."));}
        catch(RuntimeException e) {throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,"실시간 시세 저장소를 확인하세요. DB 025 적용이 필요합니다.");}
    }
    @GetMapping(value="/events",produces=MediaType.TEXT_EVENT_STREAM_VALUE)
    public synchronized ResponseEntity<SseEmitter> events(@RequestParam String stockCode) {
        validate(stockCode);
        if(clients.size()>=10) throw new ApiException(ErrorCode.VALIDATION_ERROR,"실시간 화면 연결 상한에 도달했습니다.");
        var emitter=new SseEmitter(60000L);clients.put(emitter,stockCode);
        emitter.onCompletion(() -> remove(emitter));emitter.onTimeout(() -> remove(emitter));emitter.onError(e -> remove(emitter));
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).header("X-Accel-Buffering","no").body(emitter);
    }
    private void publish() {
        for(var entry:clients.entrySet()) {
            var emitter=entry.getKey();
            if(!sending.add(emitter)) continue;
            try {sender.execute(() -> {
                try {emitter.send(SseEmitter.event().name("snapshot").data(hub.snapshot(entry.getValue(),Instant.now())));}
                catch(Exception e) {remove(emitter);emitter.complete();}
                finally {sending.remove(emitter);}
            });} catch(RejectedExecutionException e) {sending.remove(emitter);remove(emitter);emitter.complete();}
        }
    }
    private void remove(SseEmitter emitter) {clients.remove(emitter);sending.remove(emitter);}
    private void validate(String stock) {if(stock==null || !stock.matches("[0-9]{6}")) throw new ApiException(ErrorCode.VALIDATION_ERROR,"6자리 KRX 종목코드를 선택하세요.");}
    @PreDestroy void stop() {timer.shutdownNow();sender.shutdownNow();for(var client:clients.keySet()) client.complete();clients.clear();}
}
