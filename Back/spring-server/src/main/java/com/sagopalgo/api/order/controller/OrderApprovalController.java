package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmRequest;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmResponse;
import com.sagopalgo.api.order.dto.OrderApprovalPrepareResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderReconciliationHistoryItemResponse;
import com.sagopalgo.api.order.dto.OrderReconciliationReviewRequest;
import com.sagopalgo.api.order.dto.OrderReconciliationReviewResponse;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.service.OrderApprovalService;
import com.sagopalgo.api.order.service.OrderReconciliationService;
import com.sagopalgo.api.order.service.OrderSubmissionGuardService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/orders/approvals")
public class OrderApprovalController {
    private final OrderApprovalService service;
    private final OrderSubmissionGuardService submissionGuardService;
    private final OrderReconciliationService reconciliationService;
    private final LocalUserContext localUserContext;

    public OrderApprovalController(
        OrderApprovalService service,
        OrderSubmissionGuardService submissionGuardService,
        OrderReconciliationService reconciliationService,
        LocalUserContext localUserContext
    ) {
        this.service = service;
        this.submissionGuardService = submissionGuardService;
        this.reconciliationService = reconciliationService;
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

    @GetMapping("/{approvalId}/submission")
    public ResponseEntity<ApiResponse<OrderSubmissionStatusResponse>> submissionStatus(
        @PathVariable Long approvalId
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            submissionGuardService.status(localUserContext.userId(), approvalId),
            "주문 제출 가드 상태가 조회되었습니다. 이 API는 주문을 전송하지 않습니다."
        ));
    }

    @PostMapping("/{approvalId}/reconciliation-checks")
    public ResponseEntity<ApiResponse<OrderReconciliationReviewResponse>> checkReconciliation(
        @PathVariable Long approvalId,
        @Valid @RequestBody OrderReconciliationReviewRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            reconciliationService.review(localUserContext.userId(), approvalId, request),
            "KB 주문 이력 대조 결과가 기록되었습니다. 주문 접수 여부는 자동 확정되지 않습니다."
        ));
    }

    @GetMapping("/{approvalId}/reconciliation-checks")
    public ResponseEntity<ApiResponse<List<OrderReconciliationHistoryItemResponse>>> reconciliationHistory(
        @PathVariable Long approvalId
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            reconciliationService.history(localUserContext.userId(), approvalId),
            "최근 주문 대조 기록이 조회되었습니다."
        ));
    }
}
