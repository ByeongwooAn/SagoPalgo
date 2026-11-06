package com.sagopalgo.api.research.export;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.common.util.ContentHash;
import com.sagopalgo.api.market.stream.MarketAvailabilityClock;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

/** Read-only delivery evidence for a local research consumer; never a model/order trigger. */
@RestController
@RequestMapping("/api/v1/research/input-delivery")
public class ResearchInputDeliveryController {
    public record Point(Instant at,long elapsedNanos,String quality) {}
    public record Delivery(String schemaVersion,String requestId,String deliveryId,String producerClockDomain,
        Point producerReceived,Point producerSent,String payloadJson,String payloadSha256,boolean utcSynchronized) {}
    private final StoredDatasetExportService exports;
    private final MarketAvailabilityClock clock;
    private final ObjectMapper json;
    public ResearchInputDeliveryController(StoredDatasetExportService exports,MarketAvailabilityClock clock,ObjectMapper json) {
        this.exports=exports;this.clock=clock;
        this.json=json.copy().disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
    }
    @GetMapping
    public ResponseEntity<?> deliver(@RequestParam String requestId,@RequestParam String stockCode,
        @RequestParam String from,@RequestParam String to) {
        if(requestId==null || !requestId.matches("[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}"))
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"요청별 UUID가 필요합니다.");
        Instant start,end;
        try {start=Instant.parse(from);end=Instant.parse(to);}
        catch(Exception e) {throw new ApiException(ErrorCode.VALIDATION_ERROR,"시간대가 포함된 UTC 구간을 확인하세요.");}
        var received=clock.mark();
        var snapshot=exports.exportAvailability(stockCode,start,end);
        final String payload;
        try {payload=json.writeValueAsString(snapshot);}
        catch(Exception e) {throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,"입력 전달 자료를 직렬화할 수 없습니다.");}
        var sent=clock.mark();
        var envelope=new Delivery("SAGOPALGO_INPUT_DELIVERY_V1",requestId,UUID.randomUUID().toString(),clock.domain(),
            point(received),point(sent),payload,ContentHash.sha256(payload),false);
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(envelope,
            "로컬 연구 입력 전달입니다. UTC 동기화·모델 판단·주문 체결 확인과 구분합니다."));
    }
    private Point point(MarketAvailabilityClock.Mark value) {
        return new Point(value.at(),value.elapsedNanos(),value.stable()?"MONOTONIC_STABLE":"CLOCK_STEP_DETECTED");
    }
}
