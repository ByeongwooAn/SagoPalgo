package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.KbOrderLookupResponse;
import com.sagopalgo.api.order.dto.OrderReconciliationHistoryItemResponse;
import com.sagopalgo.api.order.dto.OrderReconciliationReviewRequest;
import com.sagopalgo.api.order.dto.OrderReconciliationReviewResponse;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.mapper.OrderReconciliationCheckMapper;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import com.sagopalgo.api.order.model.OrderReconciliationCheckRecord;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.springframework.stereotype.Service;

/** 읽기 전용 KB 조회 결과를 감사 기록으로 남기며 주문 가드 상태는 변경하지 않습니다. */
@Service
public class OrderReconciliationService {
    private final OrderSubmissionGuardService guardService;
    private final OrderPrecheckMapper precheckMapper;
    private final OrderReconciliationCheckMapper checkMapper;
    private final KbOrderExecutionService executionService;

    public OrderReconciliationService(
        OrderSubmissionGuardService guardService,
        OrderPrecheckMapper precheckMapper,
        OrderReconciliationCheckMapper checkMapper,
        KbOrderExecutionService executionService
    ) {
        this.guardService = guardService;
        this.precheckMapper = precheckMapper;
        this.checkMapper = checkMapper;
        this.executionService = executionService;
    }

    public OrderReconciliationReviewResponse review(
        Long userId, Long approvalId, OrderReconciliationReviewRequest request
    ) {
        OrderSubmissionStatusResponse guard = guardService.status(userId, approvalId);
        if (!List.of("RESERVED", "UNCERTAIN").contains(guard.status())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "제출 예약 또는 확인 필요 상태만 대조할 수 있습니다.");
        }
        OrderPrecheckRecord precheck = precheckMapper.findForApproval(approvalId, userId);
        if (precheck == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "승인 당시 주문안을 찾을 수 없습니다.");
        }
        KbOrderLookupResponse lookup = executionService.findByOrderNumber(
            request.orderDate(), request.orderNo()
        );
        String reviewStatus = !lookup.completeScan() ? "INCOMPLETE_SCAN"
            : lookup.matches().isEmpty() ? "NO_MATCH_IN_SCAN" : "MATCHES_REQUIRE_REVIEW";

        OrderReconciliationCheckRecord check = new OrderReconciliationCheckRecord();
        check.setOrderApprovalId(approvalId);
        check.setUserId(userId);
        check.setOrderDate(LocalDate.parse(lookup.orderDate(), DateTimeFormatter.BASIC_ISO_DATE));
        check.setOrderNo(lookup.orderNo());
        check.setCompleteScan(lookup.completeScan());
        check.setPagesScanned(lookup.pagesScanned());
        check.setMatchCount(lookup.matches().size());
        check.setReviewStatus(reviewStatus);
        check.setCheckedAt(LocalDateTime.now());
        if (checkMapper.insert(check) != 1) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "주문 대조 기록을 저장할 수 없습니다.");
        }
        return new OrderReconciliationReviewResponse(
            check.getOrderReconciliationCheckId(), approvalId, guard.status(),
            precheck.getStockCode(), precheck.getOrderSide(), precheck.getRequestedPrice(),
            precheck.getQuantity(), lookup.orderDate(), lookup.orderNo(), lookup.completeScan(),
            lookup.pagesScanned(), reviewStatus, lookup.matches(), check.getCheckedAt()
        );
    }

    public List<OrderReconciliationHistoryItemResponse> history(Long userId, Long approvalId) {
        guardService.status(userId, approvalId);
        return checkMapper.findRecentByApprovalId(approvalId, userId).stream()
            .map(check -> new OrderReconciliationHistoryItemResponse(
                check.getOrderReconciliationCheckId(), check.getOrderDate(), check.getOrderNo(),
                check.isCompleteScan(), check.getPagesScanned(), check.getMatchCount(),
                check.getReviewStatus(), check.getCheckedAt()
            ))
            .toList();
    }
}
