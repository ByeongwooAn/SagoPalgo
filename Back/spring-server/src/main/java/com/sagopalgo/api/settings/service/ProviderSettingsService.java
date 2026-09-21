package com.sagopalgo.api.settings.service;

import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.settings.dto.ProviderSettingResponse;
import com.sagopalgo.api.settings.dto.ProviderSettingsResponse;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * 민감한 API Key를 노출하지 않고 외부 데이터 Provider 연동 상태만 제공합니다.
 */
@Service
public class ProviderSettingsService {

    private final KisMarketProperties kisMarketProperties;
    private final SecuritiesProviderProperties securitiesProviderProperties;
    private final ResearchProviderProperties researchProviderProperties;

    public ProviderSettingsService(
        KisMarketProperties kisMarketProperties,
        SecuritiesProviderProperties securitiesProviderProperties,
        ResearchProviderProperties researchProviderProperties
    ) {
        this.kisMarketProperties = kisMarketProperties;
        this.securitiesProviderProperties = securitiesProviderProperties;
        this.researchProviderProperties = researchProviderProperties;
    }

    public ProviderSettingsResponse getSettings() {
        Provider kb = securitiesProviderProperties.getKb();
        Provider toss = securitiesProviderProperties.getToss();
        ResearchProviderProperties.NaverNews naver = researchProviderProperties.getNaverNews();
        ResearchProviderProperties.OpenDart openDart = researchProviderProperties.getOpenDart();

        List<String> kbMissing = kbMissingSettings(kb);
        List<String> kisMissing = missingSettings(
            entry("App Key", kisMarketProperties.getAppKey()),
            entry("App Secret", kisMarketProperties.getAppSecret())
        );
        List<String> tossMissing = missingSettings(
            entry("Base URL", toss.getBaseUrl()),
            entry("현재가 API 경로", toss.getCurrentPricePath()),
            entry("App Key", toss.getAppKey()),
            entry("App Secret", toss.getAppSecret())
        );
        List<String> naverMissing = missingSettings(
            entry("Client ID", naver.getClientId()),
            entry("Client Secret", naver.getClientSecret())
        );
        List<String> dartMissing = missingSettings(entry("API Key", openDart.getApiKey()));

        return new ProviderSettingsResponse(
            "ENV_FILE",
            ".env 파일과 Docker env-file로 개인용 API Key, App Secret, 계좌번호를 관리합니다.",
            "주문 기능 기본 OFF",
            List.of("KB", "KIS", "TOSS"),
            "앞 Provider가 비활성·미설정·조회 실패이면 다음 Provider를 시도하고, 모두 실패하면 등록 매수가를 사용합니다.",
            List.of(
                new ProviderSettingResponse(
                    "KB",
                    "KB증권",
                    kb.isMarketDataEnabled(),
                    kb.isAccountEnabled(),
                    kb.isOrderEnabled(),
                    false,
                    false,
                    kbMissing.isEmpty(),
                    kbMissing,
                    "계좌 조회와 추후 주문 기능의 기준 증권사"
                ),
                new ProviderSettingResponse(
                    "KIS",
                    "한국투자증권",
                    kisMarketProperties.isEnabled(),
                    false,
                    false,
                    false,
                    false,
                    kisMissing.isEmpty(),
                    kisMissing,
                    "국내 주식 시세 조회용 데이터 소스"
                ),
                new ProviderSettingResponse(
                    "TOSS",
                    "토스증권",
                    toss.isMarketDataEnabled(),
                    false,
                    false,
                    false,
                    false,
                    tossMissing.isEmpty(),
                    tossMissing,
                    "분석용 시세/종목 정보 보조 데이터 소스"
                ),
                new ProviderSettingResponse(
                    "NAVER_NEWS",
                    "네이버 뉴스",
                    false,
                    false,
                    false,
                    naver.isEnabled(),
                    false,
                    naverMissing.isEmpty(),
                    naverMissing,
                    "종목명 기준 최신 뉴스 검색 데이터 소스"
                ),
                new ProviderSettingResponse(
                    "OPEN_DART",
                    "OpenDART",
                    false,
                    false,
                    false,
                    false,
                    openDart.isEnabled(),
                    dartMissing.isEmpty(),
                    dartMissing,
                    "종목코드와 DART 고유번호를 연결하는 전자공시 데이터 소스"
                )
            )
        );
    }

    private List<String> kbMissingSettings(Provider kb) {
        List<SettingEntry> entries = new ArrayList<>();
        entries.add(entry("App Key", kb.getAppKey()));
        entries.add(entry("App Secret", kb.getAppSecret()));
        if (kb.isMarketDataEnabled()) {
            entries.add(entry("현재가 API 경로", kb.getCurrentPricePath()));
            entries.add(entry("통합차트 API 경로", kb.getCandlePath()));
        }
        return missingSettings(entries.toArray(SettingEntry[]::new));
    }

    private List<String> missingSettings(SettingEntry... entries) {
        return Arrays.stream(entries)
            .filter(entry -> !hasText(entry.value()))
            .map(SettingEntry::label)
            .toList();
    }

    private SettingEntry entry(String label, String value) {
        return new SettingEntry(label, value);
    }

    private boolean hasText(String value) {
        return value != null && !value.isBlank();
    }

    private record SettingEntry(String label, String value) {
    }
}
