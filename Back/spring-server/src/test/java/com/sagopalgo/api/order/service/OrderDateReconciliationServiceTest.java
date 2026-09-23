package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.KbOrderDateScanResponse;
import com.sagopalgo.api.order.dto.OrderDateReconciliationRequest;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.mapper.OrderDateReconciliationCheckMapper;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.model.OrderDateReconciliationCheckRecord;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderDateReconciliationServiceTest {
    @Mock private OrderSubmissionGuardService guardService;
    @Mock private OrderPrecheckMapper precheckMapper;
    @Mock private OrderDateReconciliationCheckMapper checkMapper;
    @Mock private KbOrderExecutionService executionService;
    private OrderDateReconciliationService service;

    @BeforeEach
    void setUp() {
        service = new OrderDateReconciliationService(
            guardService, precheckMapper, checkMapper, executionService
        );
    }

    @Test
    void storesIncompleteDateScanWithoutChangingGuard() {
        allowReview("UNCERTAIN");
        when(executionService.scanDate("20260923"))
            .thenReturn(new KbOrderDateScanResponse("20260923", false, 10, true, List.of()));
        when(checkMapper.insert(any())).thenAnswer(invocation -> {
            OrderDateReconciliationCheckRecord record = invocation.getArgument(0);
            record.setOrderDateReconciliationCheckId(21L);
            return 1;
        });

        var result = service.review(1L, 7L, new OrderDateReconciliationRequest("20260923"));

        assertThat(result.checkId()).isEqualTo(21L);
        assertThat(result.guardStatus()).isEqualTo("UNCERTAIN");
        assertThat(result.completeScan()).isFalse();
        assertThat(result.itemLimitReached()).isTrue();
        assertThat(result.stockCode()).isEqualTo("005930");
        ArgumentCaptor<OrderDateReconciliationCheckRecord> saved =
            ArgumentCaptor.forClass(OrderDateReconciliationCheckRecord.class);
        verify(checkMapper).insert(saved.capture());
        assertThat(saved.getValue().getOrderDate()).isEqualTo(LocalDate.of(2026, 9, 23));
        assertThat(saved.getValue().isCompleteScan()).isFalse();
        verify(guardService, never()).reserveOnce(any(), any());
        verify(guardService, never()).markUncertain(any(), any());
    }

    @Test
    void readyApprovalCannotScanBrokerHistory() {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, "READY", null, null));

        assertThatThrownBy(() -> service.review(
            1L, 7L, new OrderDateReconciliationRequest("20260923")
        )).isInstanceOf(ApiException.class);
        verify(executionService, never()).scanDate(any());
        verify(checkMapper, never()).insert(any());
    }

    @Test
    void brokerFailureDoesNotCreateSuccessfulAuditRecord() {
        allowReview("RESERVED");
        when(executionService.scanDate("20260923"))
            .thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR));

        assertThatThrownBy(() -> service.review(
            1L, 7L, new OrderDateReconciliationRequest("20260923")
        )).isInstanceOf(ApiException.class);
        verify(checkMapper, never()).insert(any());
    }

    @Test
    void historyIsScopedToOwnedApproval() {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, "UNCERTAIN", null, null));
        OrderDateReconciliationCheckRecord record = new OrderDateReconciliationCheckRecord();
        record.setOrderDateReconciliationCheckId(21L);
        record.setOrderDate(LocalDate.of(2026, 9, 23));
        record.setRowCount(3);
        when(checkMapper.findRecentByApprovalId(7L, 1L)).thenReturn(List.of(record));

        assertThat(service.history(1L, 7L)).extracting(item -> item.rowCount()).containsExactly(3);
    }

    private void allowReview(String status) {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, status, null, null));
        OrderPrecheckRecord precheck = new OrderPrecheckRecord();
        precheck.setStockCode("005930");
        precheck.setOrderSide("BUY");
        precheck.setRequestedPrice(new BigDecimal("75000"));
        precheck.setQuantity(new BigDecimal("2"));
        when(precheckMapper.findForApproval(7L, 1L)).thenReturn(precheck);
    }
}
