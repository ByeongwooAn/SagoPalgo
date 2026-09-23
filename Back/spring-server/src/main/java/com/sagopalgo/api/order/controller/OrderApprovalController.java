package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmRequest;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmResponse;
import com.sagopalgo.api.order.dto.OrderApprovalPrepareResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.service.OrderApprovalService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders/approvals")
public class OrderApprovalController {
    private final OrderApprovalService service;
    private final LocalUserContext localUserContext;

    public OrderApprovalController(OrderApprovalService service, LocalUserContext localUserContext) {
        this.service = service;
        this.localUserContext = localUserContext;
    }

    @PostMapping("/prepare")
    public ResponseEntity<ApiResponse<OrderApprovalPrepareResponse>> prepare(
        @Valid @RequestBody OrderPrecheckRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.prepare(localUserContext.userId(), request),
            "주문 승인 준비가 완료되었습니다. 실제 주문은 전송되지 않았습니다."
        ));
    }

    @PostMapping("/confirm")
    public ResponseEntity<ApiResponse<OrderApprovalConfirmResponse>> confirm(
        @Valid @RequestBody OrderApprovalConfirmRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.confirm(localUserContext.userId(), request),
            "수동 승인 기록이 저장되었습니다. 실제 주문은 전송되지 않았습니다."
        ));
    }
}
