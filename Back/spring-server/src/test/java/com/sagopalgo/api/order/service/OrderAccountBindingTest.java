package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import org.junit.jupiter.api.Test;

class OrderAccountBindingTest {
    @Test
    void fingerprintDoesNotExposeAccountAndChangesWithConnectionSettings() {
        SecuritiesProviderProperties properties = properties();
        OrderAccountBinding binding = new OrderAccountBinding(properties);
        String original = binding.requireFingerprint();

        assertThat(original).matches("[0-9a-f]{64}").doesNotContain("12345678");
        assertThat(binding.matches(original)).isTrue();
        properties.getKb().setAccountNumber("87654321");
        assertThat(binding.matches(original)).isFalse();
        properties.getKb().setAccountNumber("12345678");
        properties.getKb().setAccountProductCode("02");
        assertThat(binding.matches(original)).isFalse();
        properties.getKb().setAccountProductCode("01");
        properties.getKb().setAppSecret("rotated-secret");
        assertThat(binding.matches(original)).isFalse();
    }

    @Test
    void missingCredentialsFailClosed() {
        SecuritiesProviderProperties properties = properties();
        properties.getKb().setAccountNumber("");
        OrderAccountBinding binding = new OrderAccountBinding(properties);

        assertThat(binding.matches("old-fingerprint")).isFalse();
        assertThatThrownBy(binding::requireFingerprint).isInstanceOf(ApiException.class);
    }

    private SecuritiesProviderProperties properties() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        properties.getKb().setBaseUrl("https://example.test");
        properties.getKb().setAppKey("app-key");
        properties.getKb().setAppSecret("app-secret");
        properties.getKb().setAccountNumber("12345678");
        properties.getKb().setAccountProductCode("01");
        return properties;
    }
}
