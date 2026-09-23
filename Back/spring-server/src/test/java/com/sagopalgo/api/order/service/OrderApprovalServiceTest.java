package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmRequest;
import com.sagopalgo.api.order.dto.OrderApprovalPrepareResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderPrecheckResponse;
import com.sagopalgo.api.order.mapper.OrderApprovalMapper;
import com.sagopalgo.api.order.mapper.OrderSubmissionGuardMapper;
import com.sagopalgo.api.order.model.OrderApprovalRecord;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderApprovalServiceTest {
    @Mock private OrderPrecheckService precheckService;
    @Mock private OrderApprovalMapper mapper;
    @Mock private OrderSubmissionGuardMapper submissionGuardMapper;

    private OrderApprovalService service;

    @BeforeEach
    void setUp() {
        service = new OrderApprovalService(precheckService, mapper, submissionGuardMapper);
    }

    @Test
    void preparesFreshEligiblePrecheckWithHashedShortLivedToken() {
        OrderPrecheckRequest request = request("100", "2");
        OrderPrecheckResponse precheck = precheck(true);
        when(precheckService.precheck(1L, request)).thenReturn(precheck);
        when(mapper.insert(any())).thenAnswer(invocation -> {
            OrderApprovalRecord record = invocation.getArgument(0);
            record.setOrderApprovalId(7L);
            return 1;
        });

        OrderApprovalPrepareResponse response = service.prepare(1L, request);

        ArgumentCaptor<OrderApprovalRecord> captor = ArgumentCaptor.forClass(OrderApprovalRecord.class);
        verify(mapper).insert(captor.capture());
        OrderApprovalRecord stored = captor.getValue();
        assertThat(response.approvalId()).isEqualTo(7L);
        assertThat(response.precheck()).isSameAs(precheck);
        assertThat(response.token()).hasSizeGreaterThan(30);
        assertThat(stored.getTokenHash()).matches("[0-9a-f]{64}").isNotEqualTo(response.token());
        assertThat(stored.getExpiresAt()).isEqualTo(stored.getCreatedAt().plusSeconds(90));
    }

    @Test
    void rejectsFailedPrecheckAndFractionalShareBeforeApproval() {
        OrderPrecheckRequest request = request("100", "2");
        when(precheckService.precheck(1L, request)).thenReturn(precheck(false));
        assertThatThrownBy(() -> service.prepare(1L, request)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.prepare(1L, request("100", "1.5")))
            .isInstanceOf(ApiException.class);
        verify(mapper, never()).insert(any());
    }

    @Test
    void consumesTokenOnceWithoutSubmittingAnOrder() {
        when(mapper.acknowledge(eq(7L), eq(1L), any(), any(LocalDateTime.class)))
            .thenReturn(1, 0);
        when(submissionGuardMapper.insertReady(eq(7L), eq(1L), any(LocalDateTime.class)))
            .thenReturn(1);
        OrderApprovalConfirmRequest request = new OrderApprovalConfirmRequest(7L, "one-time-token", true);

        var response = service.confirm(1L, request);

        assertThat(response.status()).isEqualTo("ACKNOWLEDGED");
        assertThat(response.orderSubmitted()).isFalse();
        assertThatThrownBy(() -> service.confirm(1L, request)).isInstanceOf(ApiException.class);
        verify(submissionGuardMapper).insertReady(eq(7L), eq(1L), any(LocalDateTime.class));
    }

    @Test
    void failsConfirmationWhenGuardCannotBeCreated() {
        when(mapper.acknowledge(eq(7L), eq(1L), any(), any(LocalDateTime.class))).thenReturn(1);
        assertThatThrownBy(() -> service.confirm(
            1L, new OrderApprovalConfirmRequest(7L, "one-time-token", true)
        )).isInstanceOf(ApiException.class);
    }

    @Test
    void refusesConfirmationWithoutExplicitAcknowledgement() {
        assertThatThrownBy(() -> service.confirm(1L, new OrderApprovalConfirmRequest(7L, "token", false)))
            .isInstanceOf(ApiException.class);
        verify(mapper, never()).acknowledge(any(), any(), any(), any());
        verify(submissionGuardMapper, never()).insertReady(any(), any(), any());
    }

    private OrderPrecheckRequest request(String price, String quantity) {
        return new OrderPrecheckRequest(
            "005930", "삼성전자", "KOSPI", "BUY", new BigDecimal(price), new BigDecimal(quantity)
        );
    }

    private OrderPrecheckResponse precheck(boolean eligible) {
        return new OrderPrecheckResponse(
            31L, "005930", "삼성전자", "KOSPI", "BUY", "LIMIT",
            new BigDecimal("100"), new BigDecimal("2"), new BigDecimal("200"),
            "KB", new BigDecimal("100"), BigDecimal.ZERO, new BigDecimal("1000"),
            BigDecimal.ZERO, new BigDecimal("1000000"), new BigDecimal("5"),
            true, eligible, false, "실제 주문 미전송", java.util.List.of(), LocalDateTime.now()
        );
    }
}
