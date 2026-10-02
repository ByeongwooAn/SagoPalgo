package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.order.dto.KbOrderExecutionPageResponse;
import com.sagopalgo.api.order.mapper.OrderReadOnlyProbeMapper;
import com.sagopalgo.api.order.model.OrderReadOnlyProbeRecord;
import java.time.LocalDateTime;
import java.util.Optional;
import org.mockito.ArgumentCaptor;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderReadOnlyProbeServiceTest {
    @Mock private KbOrderExecutionService executionService;
    @Mock private OrderReadOnlyProbeMapper probeMapper;

    @Test
    void blocksWithoutAccountConfigurationAndDoesNotCallKb() {
        OrderReadOnlyProbeService service = new OrderReadOnlyProbeService(
            new OrderReadinessService(new SecuritiesProviderProperties()), executionService, probeMapper
        );

        var response = service.probe(1L);

        assertThat(response.status()).isEqualTo("CONFIGURATION_BLOCKED");
        assertThat(response.readOnly()).isTrue();
        verify(executionService, never()).page(org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
        verifyStoredResult(1L, "CONFIGURATION_BLOCKED", response.orderDate());
    }

    @Test
    void verifiesOnlyOneReadOnlyPageWithoutExposingOrderRows() {
        OrderReadOnlyProbeService service = configuredService();
        when(executionService.page(org.mockito.ArgumentMatchers.matches("[0-9]{8}"),
            org.mockito.ArgumentMatchers.eq("0"), org.mockito.ArgumentMatchers.eq("")))
            .thenAnswer(invocation -> new KbOrderExecutionPageResponse(
                invocation.getArgument(0), "0", "", "", java.util.List.of()
            ));

        var response = service.probe(1L);

        assertThat(response.status()).isEqualTo("VERIFIED");
        assertThat(response.orderDate()).matches("[0-9]{8}");
        assertThat(response.readOnly()).isTrue();
        assertThat(response.toString()).doesNotContain("12345678", "private-key", "private-secret");
        verify(executionService).page(response.orderDate(), "0", "");
        verifyStoredResult(1L, "VERIFIED", response.orderDate());
    }

    @Test
    void externalFailureIsUnverifiedWithoutLeakingBrokerMessage() {
        OrderReadOnlyProbeService service = configuredService();
        when(executionService.page(org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.eq("0"), org.mockito.ArgumentMatchers.eq("")))
            .thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "private broker response"));

        var response = service.probe(1L);

        assertThat(response.status()).isEqualTo("UNVERIFIED");
        assertThat(response.message()).doesNotContain("private broker response");
        assertThat(response.readOnly()).isTrue();
        verifyStoredResult(1L, "UNVERIFIED", response.orderDate());
    }

    @Test
    void latestReadsOnlyTheRequestedUsersSanitizedResult() {
        OrderReadOnlyProbeService service = configuredService();
        LocalDateTime checkedAt = LocalDateTime.of(2026, 9, 30, 10, 0);
        when(probeMapper.findLatest(2L)).thenReturn(Optional.of(
            new OrderReadOnlyProbeRecord(2L, "VERIFIED", "20260930", checkedAt)
        ));

        var response = service.latest(2L).orElseThrow();

        assertThat(response.status()).isEqualTo("VERIFIED");
        assertThat(response.checkedAt()).isEqualTo(checkedAt);
        assertThat(response.readOnly()).isTrue();
        assertThat(response.message()).contains("주문 권한이나 전송 가능 상태를 뜻하지 않습니다");
        verify(probeMapper).findLatest(2L);
        verify(executionService, never()).page(org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void latestReturnsEmptyBeforeAnyManualProbe() {
        OrderReadOnlyProbeService service = configuredService();
        when(probeMapper.findLatest(2L)).thenReturn(Optional.empty());

        assertThat(service.latest(2L)).isEmpty();
        verify(probeMapper).findLatest(2L);
    }

    private void verifyStoredResult(Long userId, String status, String orderDate) {
        ArgumentCaptor<OrderReadOnlyProbeRecord> captor = ArgumentCaptor.forClass(OrderReadOnlyProbeRecord.class);
        verify(probeMapper).insert(captor.capture());
        assertThat(captor.getValue().userId()).isEqualTo(userId);
        assertThat(captor.getValue().status()).isEqualTo(status);
        assertThat(captor.getValue().orderDate()).isEqualTo(orderDate);
        assertThat(captor.getValue().checkedAt()).isNotNull();
        assertThat(captor.getValue().toString()).doesNotContain("12345678", "private-key", "private-secret");
    }

    private OrderReadOnlyProbeService configuredService() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        var kb = properties.getKb();
        kb.setAccountEnabled(true);
        kb.setAppKey("private-key");
        kb.setAppSecret("private-secret");
        kb.setAccountNumber("12345678");
        kb.setBaseUrl("https://example.test");
        return new OrderReadOnlyProbeService(new OrderReadinessService(properties), executionService, probeMapper);
    }
}
