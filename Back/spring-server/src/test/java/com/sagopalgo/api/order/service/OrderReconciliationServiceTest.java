package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse;
import com.sagopalgo.api.order.dto.KbOrderLookupResponse;
import com.sagopalgo.api.order.dto.OrderReconciliationReviewRequest;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.mapper.OrderReconciliationCheckMapper;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import com.sagopalgo.api.order.model.OrderReconciliationCheckRecord;
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
class OrderReconciliationServiceTest {
    @Mock private OrderSubmissionGuardService guardService;
    @Mock private OrderPrecheckMapper precheckMapper;
    @Mock private OrderReconciliationCheckMapper checkMapper;
    @Mock private KbOrderExecutionService executionService;
    private OrderReconciliationService service;

    @BeforeEach
    void setUp() {
        service = new OrderReconciliationService(
            guardService, precheckMapper, checkMapper, executionService
        );
    }

    @Test
    void recordsMatchesForManualReviewWithoutResolvingGuard() {
        readyForReview("UNCERTAIN");
        KbOrderExecutionItemResponse item = new KbOrderExecutionItemResponse(
            "1234567890", "005930", "삼성전자", "매수", "101530",
            new BigDecimal("2"), BigDecimal.ZERO, new BigDecimal("2"),
            new BigDecimal("100"), null, "", "OPEN"
        );
        when(executionService.findByOrderNumber("20260923", "1234567890"))
            .thenReturn(new KbOrderLookupResponse("20260923", "1234567890", true, 2, List.of(item)));
        when(checkMapper.insert(any())).thenAnswer(invocation -> {
            OrderReconciliationCheckRecord record = invocation.getArgument(0);
            record.setOrderReconciliationCheckId(41L);
            return 1;
        });

        var result = service.review(1L, 7L, new OrderReconciliationReviewRequest("20260923", "1234567890"));

        assertThat(result.checkId()).isEqualTo(41L);
        assertThat(result.guardStatus()).isEqualTo("UNCERTAIN");
        assertThat(result.reviewStatus()).isEqualTo("MATCHES_REQUIRE_REVIEW");
        assertThat(result.matches()).containsExactly(item);
        assertThat(result.stockCode()).isEqualTo("005930");
        ArgumentCaptor<OrderReconciliationCheckRecord> saved =
            ArgumentCaptor.forClass(OrderReconciliationCheckRecord.class);
        verify(checkMapper).insert(saved.capture());
        assertThat(saved.getValue().getOrderDate()).isEqualTo(LocalDate.of(2026, 9, 23));
        assertThat(saved.getValue().getMatchCount()).isEqualTo(1);
        verify(guardService, never()).reserveOnce(any(), any());
        verify(guardService, never()).markUncertain(any(), any());
    }

    @Test
    void incompleteAndEmptyScansRemainNonDefinitive() {
        readyForReview("RESERVED");
        when(executionService.findByOrderNumber("20260923", "1234567890"))
            .thenReturn(new KbOrderLookupResponse("20260923", "1234567890", false, 10, List.of()),
                new KbOrderLookupResponse("20260923", "1234567890", true, 1, List.of()));
        when(checkMapper.insert(any())).thenReturn(1);
        var request = new OrderReconciliationReviewRequest("20260923", "1234567890");

        assertThat(service.review(1L, 7L, request).reviewStatus()).isEqualTo("INCOMPLETE_SCAN");
        assertThat(service.review(1L, 7L, request).reviewStatus()).isEqualTo("NO_MATCH_IN_SCAN");
    }

    @Test
    void readyOrLegacyApprovalCannotStartReconciliation() {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, "READY", null, null),
                new OrderSubmissionStatusResponse(7L, "LEGACY_REVIEW", null, null));
        var request = new OrderReconciliationReviewRequest("20260923", "1234567890");

        assertThatThrownBy(() -> service.review(1L, 7L, request)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.review(1L, 7L, request)).isInstanceOf(ApiException.class);
        verify(executionService, never()).findByOrderNumber(any(), any());
        verify(checkMapper, never()).insert(any());
    }

    @Test
    void lookupFailureDoesNotCreateACompletedCheck() {
        readyForReview("UNCERTAIN");
        when(executionService.findByOrderNumber("20260923", "1234567890"))
            .thenThrow(new ApiException(com.sagopalgo.api.common.exception.ErrorCode.EXTERNAL_DATA_ERROR));

        assertThatThrownBy(() -> service.review(
            1L, 7L, new OrderReconciliationReviewRequest("20260923", "1234567890")
        )).isInstanceOf(ApiException.class);
        verify(checkMapper, never()).insert(any());
    }

    @Test
    void historyRequiresOwnedApproval() {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, "UNCERTAIN", null, null));
        OrderReconciliationCheckRecord check = new OrderReconciliationCheckRecord();
        check.setOrderReconciliationCheckId(41L);
        check.setOrderDate(LocalDate.of(2026, 9, 23));
        check.setOrderNo("1234567890");
        check.setReviewStatus("INCOMPLETE_SCAN");
        when(checkMapper.findRecentByApprovalId(7L, 1L)).thenReturn(List.of(check));

        assertThat(service.history(1L, 7L)).extracting(item -> item.reviewStatus())
            .containsExactly("INCOMPLETE_SCAN");
    }

    private void readyForReview(String status) {
        when(guardService.status(1L, 7L))
            .thenReturn(new OrderSubmissionStatusResponse(7L, status, null, null));
        OrderPrecheckRecord precheck = new OrderPrecheckRecord();
        precheck.setStockCode("005930");
        precheck.setOrderSide("BUY");
        precheck.setRequestedPrice(new BigDecimal("100"));
        precheck.setQuantity(new BigDecimal("2"));
        when(precheckMapper.findForApproval(7L, 1L)).thenReturn(precheck);
    }
}
