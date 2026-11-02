package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.service.KbAccountSnapshotService;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class KbAccountSnapshotController {
    private final KbAccountSnapshotService service;

    public KbAccountSnapshotController(KbAccountSnapshotService service) {
        this.service = service;
    }

    @GetMapping("/api/v1/kb/accounts/primary/snapshot")
    public ResponseEntity<ApiResponse<KbAccountSnapshotResponse>> snapshot(
        @RequestParam(required = false) String orderDate
    ) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(
            ApiResponse.success(service.observe(orderDate), "KB 계좌 읽기 관찰 결과입니다. 원장·주문 가능 판정이 아닙니다.")
        );
    }
}
