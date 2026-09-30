package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.order.dto.KbOrderExecutionPageResponse;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderReadOnlyProbeServiceTest {
    @Mock private KbOrderExecutionService executionService;

    @Test
    void blocksWithoutAccountConfigurationAndDoesNotCallKb() {
        OrderReadOnlyProbeService service = new OrderReadOnlyProbeService(
            new OrderReadinessService(new SecuritiesProviderProperties()), executionService
        );

        var response = service.probe();

        assertThat(response.status()).isEqualTo("CONFIGURATION_BLOCKED");
        assertThat(response.readOnly()).isTrue();
        verify(executionService, never()).page(org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.any(), org.mockito.ArgumentMatchers.any());
    }

    @Test
    void verifiesOnlyOneReadOnlyPageWithoutExposingOrderRows() {
        OrderReadOnlyProbeService service = configuredService();
        when(executionService.page(org.mockito.ArgumentMatchers.matches("[0-9]{8}"),
            org.mockito.ArgumentMatchers.eq("0"), org.mockito.ArgumentMatchers.eq("")))
            .thenAnswer(invocation -> new KbOrderExecutionPageResponse(
                invocation.getArgument(0), "0", "", "", java.util.List.of()
            ));

        var response = service.probe();

        assertThat(response.status()).isEqualTo("VERIFIED");
        assertThat(response.orderDate()).matches("[0-9]{8}");
        assertThat(response.readOnly()).isTrue();
        assertThat(response.toString()).doesNotContain("12345678", "private-key", "private-secret");
        verify(executionService).page(response.orderDate(), "0", "");
    }

    @Test
    void externalFailureIsUnverifiedWithoutLeakingBrokerMessage() {
        OrderReadOnlyProbeService service = configuredService();
        when(executionService.page(org.mockito.ArgumentMatchers.any(),
            org.mockito.ArgumentMatchers.eq("0"), org.mockito.ArgumentMatchers.eq("")))
            .thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "private broker response"));

        var response = service.probe();

        assertThat(response.status()).isEqualTo("UNVERIFIED");
        assertThat(response.message()).doesNotContain("private broker response");
        assertThat(response.readOnly()).isTrue();
    }

    private OrderReadOnlyProbeService configuredService() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        var kb = properties.getKb();
        kb.setAccountEnabled(true);
        kb.setAppKey("private-key");
        kb.setAppSecret("private-secret");
        kb.setAccountNumber("12345678");
        kb.setBaseUrl("https://example.test");
        return new OrderReadOnlyProbeService(new OrderReadinessService(properties), executionService);
    }
}
