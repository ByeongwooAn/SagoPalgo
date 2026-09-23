package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.KbOrderDateScanResponse;
import com.sagopalgo.api.order.dto.OrderDateReconciliationHistoryItemResponse;
import com.sagopalgo.api.order.dto.OrderDateReconciliationRequest;
import com.sagopalgo.api.order.dto.OrderDateReconciliationResponse;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.mapper.OrderDateReconciliationCheckMapper;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.model.OrderDateReconciliationCheckRecord;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.springframework.stereotype.Service;

/** 주문번호 없는 날짜별 KB 조회를 수동 검토 자료로만 제공합니다. */
@Service
public class OrderDateReconciliationService {
    private final OrderSubmissionGuardService guardService;
    private final OrderPrecheckMapper precheckMapper;
    private final OrderDateReconciliationCheckMapper checkMapper;
    private final KbOrderExecutionService executionService;

    public OrderDateReconciliationService(
        OrderSubmissionGuardService guardService,
        OrderPrecheckMapper precheckMapper,
        OrderDateReconciliationCheckMapper checkMapper,
        KbOrderExecutionService executionService
    ) {
        this.guardService = guardService;
        this.precheckMapper = precheckMapper;
        this.checkMapper = checkMapper;
        this.executionService = executionService;
    }

    public OrderDateReconciliationResponse review(
        Long userId, Long approvalId, OrderDateReconciliationRequest request
    ) {
        OrderSubmissionStatusResponse guard = guardService.status(userId, approvalId);
        if (!List.of("RESERVED", "UNCERTAIN").contains(guard.status())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "제출 예약 또는 확인 필요 상태만 대조할 수 있습니다.");
        }
        OrderPrecheckRecord precheck = precheckMapper.findForApproval(approvalId, userId);
        if (precheck == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "승인 당시 주문안을 찾을 수 없습니다.");
        }
        KbOrderDateScanResponse scan = executionService.scanDate(request.orderDate());
        OrderDateReconciliationCheckRecord check = new OrderDateReconciliationCheckRecord();
        check.setOrderApprovalId(approvalId);
        check.setUserId(userId);
        check.setOrderDate(LocalDate.parse(scan.orderDate(), DateTimeFormatter.BASIC_ISO_DATE));
        check.setCompleteScan(scan.completeScan());
        check.setPagesScanned(scan.pagesScanned());
        check.setRowCount(scan.items().size());
        check.setItemLimitReached(scan.itemLimitReached());
        check.setCheckedAt(LocalDateTime.now());
        if (checkMapper.insert(check) != 1) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "날짜별 주문 대조 기록을 저장할 수 없습니다.");
        }
        return new OrderDateReconciliationResponse(
            check.getOrderDateReconciliationCheckId(), approvalId, guard.status(),
            precheck.getStockCode(), precheck.getOrderSide(), precheck.getRequestedPrice(),
            precheck.getQuantity(), scan.orderDate(), scan.completeScan(), scan.pagesScanned(),
            scan.itemLimitReached(), scan.items(), check.getCheckedAt()
        );
    }

    public List<OrderDateReconciliationHistoryItemResponse> history(Long userId, Long approvalId) {
        guardService.status(userId, approvalId);
        return checkMapper.findRecentByApprovalId(approvalId, userId).stream()
            .map(check -> new OrderDateReconciliationHistoryItemResponse(
                check.getOrderDateReconciliationCheckId(), check.getOrderDate(),
                check.isCompleteScan(), check.getPagesScanned(), check.getRowCount(),
                check.isItemLimitReached(), check.getCheckedAt()
            ))
            .toList();
    }
}
