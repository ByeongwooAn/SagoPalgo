package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.order.dto.OrderReadinessResponse;
import org.junit.jupiter.api.Test;

class OrderReadinessServiceTest {
    @Test
    void remainsBlockedWhenEveryConfiguredPrerequisitePasses() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider kb = properties.getKb();
        kb.setAccountEnabled(true);
        kb.setOrderEnabled(true);
        kb.setLiveOrderEnabled(true);
        kb.setAppKey("private-key");
        kb.setAppSecret("private-secret");
        kb.setAccountNumber("12345678");
        kb.setBaseUrl("https://developer.kbsec.com:32484");
        kb.setTokenPath("/oauth2/token");
        kb.setOrderIpAddress("192.168.1.12");
        kb.setOrderMacAddress("02:11:22:33:44:55");

        OrderReadinessResponse response = new OrderReadinessService(properties).status();

        assertThat(response.canSubmit()).isFalse();
        assertThat(response.checks()).filteredOn(check -> !check.passed())
            .extracting("code").containsExactly("SUBMISSION_TRANSPORT");
        assertThat(response.toString()).doesNotContain(
            "private-key", "private-secret", "12345678", "192.168.1.12", "02:11:22:33:44:55"
        );
        var commands=org.mockito.Mockito.mock(com.sagopalgo.api.order.mapper.ManualOrderMapper.class);
        assertThat(new OrderReadinessService(properties, commands).status().canSubmit()).isTrue();
        org.mockito.Mockito.when(commands.verifyStorage()).thenThrow(new org.springframework.dao.DataAccessResourceFailureException("private"));
        assertThat(new OrderReadinessService(properties, commands).status().canSubmit()).isFalse();
    }

    @Test
    void rejectsPlaceholderAndMalformedOperatingAddresses() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider kb = properties.getKb();
        kb.setOrderIpAddress("127.0.0.1");
        kb.setOrderMacAddress("00:00:00:00:00:00");
        OrderReadinessService service = new OrderReadinessService(properties);

        assertThat(service.status().checks()).filteredOn(check -> !check.passed())
            .extracting("code").contains("ORDER_IP", "ORDER_MAC");

        kb.setOrderIpAddress("999.1.2.3");
        kb.setOrderMacAddress("01:11:22:33:44:55");
        assertThat(service.status().checks()).filteredOn(check -> !check.passed())
            .extracting("code").contains("ORDER_IP", "ORDER_MAC");
    }

    @Test
    void defaultsToLiveOrderDisabled() {
        OrderReadinessResponse response = new OrderReadinessService(
            new SecuritiesProviderProperties()
        ).status();

        assertThat(response.canSubmit()).isFalse();
        assertThat(response.checks()).filteredOn(check -> check.code().equals("LIVE_ORDER_SWITCH"))
            .singleElement().satisfies(check -> assertThat(check.passed()).isFalse());
    }
}
