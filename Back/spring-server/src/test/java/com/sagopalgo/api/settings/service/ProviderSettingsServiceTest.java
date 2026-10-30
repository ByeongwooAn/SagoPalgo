package com.sagopalgo.api.settings.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.order.service.OrderReadinessService;
import com.sagopalgo.api.settings.dto.ProviderSettingsResponse;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 증권사 연동 설정 응답이 민감정보 없이 역할과 설정 여부만 노출하는지 검증합니다.
 */
class ProviderSettingsServiceTest {

    @Test
    @DisplayName("시장 뉴스 공시 Provider 상태와 누락 설정을 민감정보 없이 반환한다")
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
        kb.setBaseUrl("https://kb.test");
        kb.setTokenPath("/oauth/token");
        kb.setHoldingsPath("/holdings");
        kb.setSettlementBalancePath("/settlement");
        kb.setExecutionBalancePath("/execution");
        kb.setAccountNumber("12345678");
        securitiesProperties.setKb(kb);

        Provider toss = new Provider();
        toss.setMarketDataEnabled(true);
        toss.setAppKey("toss-app-key");
        toss.setAppSecret("toss-app-secret");
        toss.setBaseUrl("https://toss.test");
        toss.setTokenPath("/oauth2/token");
        toss.setCurrentPricePath("/prices");
        toss.setCandlePath("/candles");
        toss.setStockInfoPath("/stocks");
        securitiesProperties.setToss(toss);

        ResearchProviderProperties researchProperties = new ResearchProviderProperties();
        researchProperties.getNaverNews().setEnabled(true);
        researchProperties.getNaverNews().setClientId("naver-client-id");
        researchProperties.getNaverNews().setClientSecret("naver-client-secret");
        researchProperties.getOpenDart().setEnabled(true);

        ProviderSettingsService service = new ProviderSettingsService(
            kisProperties,
            securitiesProperties,
            researchProperties,
            new OrderReadinessService(securitiesProperties)
        );

        ProviderSettingsResponse response = service.getSettings();

        assertThat(response.secretStorageType()).isEqualTo("ENV_FILE");
        assertThat(response.orderSafetyMode()).isEqualTo("주문 기능 OFF · 사전검증만 지원");
        assertThat(response.orderReadiness().canSubmit()).isFalse();
        assertThat(response.orderReadiness().toString()).doesNotContain(
            "kb-app-key", "kb-app-secret", "12345678"
        );
        assertThat(response.marketDataFallbackOrder()).containsExactly("KB", "KIS", "TOSS");
        assertThat(response.providers())
            .extracting("code")
            .containsExactly("KB", "KIS", "TOSS", "NAVER_NEWS", "OPEN_DART");
        assertThat(response.providers())
            .allSatisfy(provider -> assertThat(provider.toString())
                .doesNotContain(
                    "kb-app-key",
                    "kb-app-secret",
                    "kis-app-key",
                    "kis-app-secret",
                    "toss-app-key",
                    "naver-client-secret"
                ));
        assertThat(response.providers().get(0).configured()).isTrue();
        assertThat(response.providers().get(0).accountEnabled()).isTrue();
        assertThat(response.providers().get(0).orderEnabled()).isFalse();
        assertThat(response.providers().get(1).configured()).isTrue();
        assertThat(response.providers().get(2).configured()).isTrue();
        assertThat(response.providers().get(3).newsEnabled()).isTrue();
        assertThat(response.providers().get(3).configured()).isTrue();
        assertThat(response.providers().get(4).disclosureEnabled()).isTrue();
        assertThat(response.providers().get(4).configured()).isFalse();
        assertThat(response.providers().get(4).missingRequiredSettings()).containsExactly("API Key");
    }
    @Test
    void kbReadConfigurationDoesNotRequireOrderAccountNumberButNeedsApiPaths() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider kb = properties.getKb();
        kb.setAccountEnabled(true);
        kb.setAppKey("key"); kb.setAppSecret("secret");
        kb.setBaseUrl("https://kb.test"); kb.setTokenPath("/token");
        kb.setHoldingsPath("/holdings"); kb.setSettlementBalancePath("/settlement");
        kb.setExecutionBalancePath("/execution");
        ProviderSettingsService service = new ProviderSettingsService(new KisMarketProperties(), properties,
            new ResearchProviderProperties(), new OrderReadinessService(properties));

        var settings = service.getSettings();
        assertThat(settings.providers().get(0).configured()).isTrue();
        assertThat(settings.orderReadiness().checks().stream().filter(check -> "ACCOUNT_NUMBER".equals(check.code()))
            .findFirst().orElseThrow().passed()).isFalse();

        kb.setSettlementBalancePath("");
        var incomplete = service.getSettings().providers().get(0);
        assertThat(incomplete.configured()).isFalse();
        assertThat(incomplete.missingRequiredSettings()).containsExactly("결제기준 잔고 API 경로");
        assertThat(incomplete.accountConfigured()).isFalse();

        kb.setSettlementBalancePath("/settlement");
        kb.setMarketDataEnabled(true);
        var accountOnly = service.getSettings().providers().get(0);
        assertThat(accountOnly.configured()).isFalse();
        assertThat(accountOnly.accountConfigured()).isTrue();
    }
}
