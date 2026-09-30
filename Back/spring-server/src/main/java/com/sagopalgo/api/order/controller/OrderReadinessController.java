package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.OrderReadinessResponse;
import com.sagopalgo.api.order.dto.OrderReadOnlyProbeResponse;
import com.sagopalgo.api.order.service.OrderReadOnlyProbeService;
import com.sagopalgo.api.order.service.OrderReadinessService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders/readiness")
public class OrderReadinessController {
    private final OrderReadinessService service;
    private final OrderReadOnlyProbeService probeService;

    public OrderReadinessController(OrderReadinessService service, OrderReadOnlyProbeService probeService) {
        this.service = service;
        this.probeService = probeService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<OrderReadinessResponse>> status() {
        return ResponseEntity.ok(ApiResponse.success(
            service.status(), "KB 주문 준비 상태가 조회되었습니다. 실제 주문 전송은 지원하지 않습니다."
        ));
    }

    @PostMapping("/probe")
    public ResponseEntity<ApiResponse<OrderReadOnlyProbeResponse>> probe() {
        return ResponseEntity.ok(ApiResponse.success(
            probeService.probe(), "KB 주문 이력의 읽기 전용 조회 상태를 점검했습니다."
        ));
    }
}
