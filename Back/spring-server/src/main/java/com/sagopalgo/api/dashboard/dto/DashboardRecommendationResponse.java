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
    List<DashboardRecommendationReasonResponse> reasons,
    String recommendationType,
    String analysisContext,
    String machineStatus,
    java.time.LocalDateTime createdAt,
    com.sagopalgo.api.recommendation.dto.AnalysisEvidence evidence
) {
    public DashboardRecommendationResponse(Long id, String name, String code, String market, String status,
        int score, BigDecimal price, BigDecimal stop, String summary, List<DashboardRecommendationReasonResponse> reasons) {
        this(id, name, code, market, status, score, price, stop, summary, reasons, "HOLD", "HOLDING", null, null, null);
    }
}
