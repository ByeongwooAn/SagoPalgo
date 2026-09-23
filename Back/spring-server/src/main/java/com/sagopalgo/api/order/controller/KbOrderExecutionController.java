package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.KbOrderExecutionPageResponse;
import com.sagopalgo.api.order.dto.KbOrderLookupResponse;
import com.sagopalgo.api.order.service.KbOrderExecutionService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/** 읽기 전용 KB 주문 상태 조회 API입니다. */
@RestController
@RequestMapping("/api/v1/orders/kb/executions")
public class KbOrderExecutionController {
    private final KbOrderExecutionService service;

    public KbOrderExecutionController(KbOrderExecutionService service) {
        this.service = service;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<KbOrderExecutionPageResponse>> page(
        @RequestParam(required = false) String orderDate,
        @RequestParam(defaultValue = "0") String classification,
        @RequestParam(required = false) String nextKey
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.page(orderDate, classification, nextKey),
            "KB 주문 체결·미체결 내역이 조회되었습니다."
        ));
    }

    @GetMapping("/{orderNo}")
    public ResponseEntity<ApiResponse<KbOrderLookupResponse>> findByOrderNumber(
        @PathVariable String orderNo,
        @RequestParam(required = false) String orderDate
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.findByOrderNumber(orderDate, orderNo),
            "KB 주문번호 대조가 완료되었습니다."
        ));
    }
}
