package com.sagopalgo.api.settings.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.settings.dto.ProviderSettingsResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 증권사 연동 설정 응답이 민감정보 없이 역할과 설정 여부만 노출하는지 검증합니다.
 */
class ProviderSettingsServiceTest {

    @Test
    @DisplayName("KB KIS Toss 증권사 설정 상태를 민감정보 없이 반환한다")
    void getSettingsReturnsProviderStatusWithoutSecrets() {
        KisMarketProperties kisProperties = new KisMarketProperties();
        kisProperties.setEnabled(true);
        kisProperties.setAppKey("kis-app-key");
        kisProperties.setAppSecret("kis-app-secret");

        SecuritiesProviderProperties securitiesProperties = new SecuritiesProviderProperties();
        Provider kb = new Provider();
        kb.setAccountEnabled(true);
        kb.setOrderEnabled(false);
        kb.setAppKey("kb-app-key");
        kb.setAppSecret("kb-app-secret");
        kb.setAccountNumber("1234567890");
        securitiesProperties.setKb(kb);

        Provider toss = new Provider();
        toss.setMarketDataEnabled(true);
        toss.setAppKey("toss-app-key");
        toss.setAppSecret("toss-app-secret");
        securitiesProperties.setToss(toss);

        ProviderSettingsService service = new ProviderSettingsService(kisProperties, securitiesProperties);

        ProviderSettingsResponse response = service.getSettings();

        assertThat(response.providers())
            .extracting("code")
            .containsExactly("KB", "KIS", "TOSS");
        assertThat(response.providers())
            .allSatisfy(provider -> assertThat(provider.toString())
                .doesNotContain("kb-app-key", "kb-app-secret", "kis-app-key", "kis-app-secret", "toss-app-key"));
        assertThat(response.providers().get(0).configured()).isTrue();
        assertThat(response.providers().get(0).accountEnabled()).isTrue();
        assertThat(response.providers().get(0).orderEnabled()).isFalse();
        assertThat(response.providers().get(1).configured()).isTrue();
        assertThat(response.providers().get(2).configured()).isTrue();
    }
}
