package com.sagopalgo.api.research.export;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.common.response.ApiResponse;
import java.time.Instant;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/research/dataset-export")
public class StoredDatasetExportController {
    private final StoredDatasetExportService service;
    public StoredDatasetExportController(StoredDatasetExportService service) { this.service = service; }
    @GetMapping("/availability")
    public ResponseEntity<?> availability(@RequestParam String stockCode,@RequestParam String from,@RequestParam String to) {
        Instant start,end;
        try {start=Instant.parse(from);end=Instant.parse(to);}
        catch(Exception e) {throw new ApiException(ErrorCode.VALIDATION_ERROR,"시간대가 포함된 UTC 구간을 확인하세요.");}
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
            service.exportAvailability(stockCode,start,end),"커밋 이후 로컬 입력 공개 관측입니다. 외부 UTC·모델 수신 확인과 구분합니다."));
    }
    @GetMapping
    public ResponseEntity<?> export(@RequestParam String stockCode, @RequestParam String from, @RequestParam String to) {
        Instant start, end;
        try { start = Instant.parse(from); end = Instant.parse(to); }
        catch (Exception e) { throw new ApiException(ErrorCode.VALIDATION_ERROR, "시간대가 포함된 UTC 구간을 확인하세요."); }
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
            service.export(stockCode, start, end), "저장된 공개 자료이며 수집 완전성은 보장하지 않습니다."));
    }
}
