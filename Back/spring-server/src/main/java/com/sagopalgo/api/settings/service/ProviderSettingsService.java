package com.sagopalgo.api.settings.service;

import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.settings.dto.ProviderSettingResponse;
import com.sagopalgo.api.settings.dto.ProviderSettingsResponse;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * 민감한 API Key를 노출하지 않고 증권사 연동 상태만 제공합니다.
 */
@Service
public class ProviderSettingsService {

    private final KisMarketProperties kisMarketProperties;
    private final SecuritiesProviderProperties securitiesProviderProperties;

    public ProviderSettingsService(
        KisMarketProperties kisMarketProperties,
        SecuritiesProviderProperties securitiesProviderProperties
    ) {
        this.kisMarketProperties = kisMarketProperties;
        this.securitiesProviderProperties = securitiesProviderProperties;
    }

    public ProviderSettingsResponse getSettings() {
        Provider kb = securitiesProviderProperties.getKb();
        Provider toss = securitiesProviderProperties.getToss();

        return new ProviderSettingsResponse(
            "ENV_FILE",
            ".env 파일과 Docker env-file로 개인용 API Key, App Secret, 계좌번호를 관리합니다.",
            "주문 기능 기본 OFF",
            List.of(
                new ProviderSettingResponse(
                    "KB",
                    "KB증권",
                    kb.isMarketDataEnabled(),
                    kb.isAccountEnabled(),
                    kb.isOrderEnabled(),
                    kb.hasRequiredSecrets() && (!kb.isAccountEnabled() || kb.hasAccountNumber()),
                    "계좌 조회와 추후 주문 기능의 기준 증권사"
                ),
                new ProviderSettingResponse(
                    "KIS",
                    "한국투자증권",
                    kisMarketProperties.isEnabled(),
                    false,
                    false,
                    hasText(kisMarketProperties.getAppKey()) && hasText(kisMarketProperties.getAppSecret()),
                    "국내 주식 시세 조회용 데이터 소스"
                ),
                new ProviderSettingResponse(
                    "TOSS",
                    "토스증권",
                    toss.isMarketDataEnabled(),
                    false,
                    false,
                    toss.hasRequiredSecrets(),
                    "분석용 시세/종목 정보 보조 데이터 소스"
                )
            )
        );
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }
}
