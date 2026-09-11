package com.sagopalgo.api.dashboard.dto;

import java.math.BigDecimal;
import java.util.List;

/**
 * 대시보드와 추천 탭에서 우선 표시할 대표 추천 DTO입니다.
 */
public record DashboardRecommendationResponse(
    Long recommendationId,
    String stockName,
    String stockCode,
    String market,
    String status,
    int score,
    BigDecimal entryPrice,
    BigDecimal stopLossRate,
    String aiSummary,
    List<DashboardRecommendationReasonResponse> reasons
) {
}
