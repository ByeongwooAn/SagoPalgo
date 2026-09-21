package com.sagopalgo.api.research.dto;

/**
 * 통합 조회 중 각 Provider가 실제로 어떻게 처리됐는지 알려줍니다.
 */
public record ResearchProviderStatusResponse(
    String provider,
    String dataType,
    String status,
    String message
) {
}
