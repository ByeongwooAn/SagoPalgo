package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.mapper.OrderSubmissionGuardMapper;
import com.sagopalgo.api.order.model.OrderSubmissionGuardRecord;
import java.time.LocalDateTime;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderSubmissionGuardServiceTest {
    @Mock private OrderSubmissionGuardMapper mapper;
    @Mock private OrderAccountBinding accountBinding;
    private OrderSubmissionGuardService service;

    @BeforeEach
    void setUp() {
        service = new OrderSubmissionGuardService(mapper, accountBinding);
    }

    @Test
    void reservesOnlyOnceForTheOwningUser() {
        when(accountBinding.requireFingerprint()).thenReturn("account-fingerprint");
        when(mapper.reserveOnce(eq(7L), eq(1L), eq("account-fingerprint"), any(LocalDateTime.class)))
            .thenReturn(1, 0);

        service.reserveOnce(1L, 7L);

        assertThatThrownBy(() -> service.reserveOnce(1L, 7L)).isInstanceOf(ApiException.class);
        verify(mapper, org.mockito.Mockito.times(2))
            .reserveOnce(eq(7L), eq(1L), eq("account-fingerprint"), any(LocalDateTime.class));
    }

    @Test
    void onlyReservedSubmissionCanBecomeUncertain() {
        when(mapper.markUncertain(eq(7L), eq(1L), any(LocalDateTime.class))).thenReturn(1, 0);

        service.markUncertain(1L, 7L);

        assertThatThrownBy(() -> service.markUncertain(1L, 7L)).isInstanceOf(ApiException.class);
    }

    @Test
    void exposesGuardStateWithoutClaimingBrokerSubmission() {
        OrderSubmissionGuardRecord record = new OrderSubmissionGuardRecord();
        record.setOrderApprovalId(7L);
        record.setUserId(1L);
        record.setStatus("READY");
        record.setAccountFingerprint("account-fingerprint");
        record.setExpiresAt(LocalDateTime.now().plusSeconds(30));
        when(mapper.findByApprovalId(7L, 1L)).thenReturn(record);
        when(accountBinding.matches("account-fingerprint")).thenReturn(true);

        var response = service.status(1L, 7L);

        assertThat(response.approvalId()).isEqualTo(7L);
        assertThat(response.status()).isEqualTo("READY");
        assertThat(response.expiresAt()).isEqualTo(record.getExpiresAt());
        assertThat(response.reservedAt()).isNull();
    }

    @Test
    void expiredAndUnboundedReadyGuardsAreNotReportedAsAvailable() {
        OrderSubmissionGuardRecord record = new OrderSubmissionGuardRecord();
        record.setOrderApprovalId(7L);
        record.setStatus("READY");
        record.setExpiresAt(LocalDateTime.now().minusSeconds(1));
        when(mapper.findByApprovalId(7L, 1L)).thenReturn(record);

        assertThat(service.status(1L, 7L).status()).isEqualTo("EXPIRED");
        record.setExpiresAt(null);
        assertThat(service.status(1L, 7L).status()).isEqualTo("EXPIRED");
    }

    @Test
    void hidesOtherUsersGuard() {
        assertThatThrownBy(() -> service.status(2L, 7L)).isInstanceOf(ApiException.class);
    }

    @Test
    void changedAccountIsVisibleAndCannotBeReserved() {
        OrderSubmissionGuardRecord record = new OrderSubmissionGuardRecord();
        record.setOrderApprovalId(7L);
        record.setStatus("READY");
        record.setAccountFingerprint("old-account-fingerprint");
        record.setExpiresAt(LocalDateTime.now().plusSeconds(30));
        when(mapper.findByApprovalId(7L, 1L)).thenReturn(record);
        when(accountBinding.requireFingerprint()).thenReturn("new-account-fingerprint");

        assertThat(service.status(1L, 7L).status()).isEqualTo("ACCOUNT_CHANGED");
        assertThatThrownBy(() -> service.reserveOnce(1L, 7L)).isInstanceOf(ApiException.class);
        verify(mapper).reserveOnce(eq(7L), eq(1L), eq("new-account-fingerprint"), any(LocalDateTime.class));
    }
}
