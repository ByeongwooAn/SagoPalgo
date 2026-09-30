package com.sagopalgo.api.recommendation.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 추천 목록과 상세 API가 반환하는 저장 추천입니다.
 */
public record RecommendationResponse(
    Long recommendationId,
    String stockCode,
    String stockName,
    String market,
    String recommendationType,
    String status,
    String statusLabel,
    int score,
    BigDecimal entryPrice,
    BigDecimal stopLossRate,
    BigDecimal takeProfitRate,
    String aiSummary,
    LocalDateTime createdAt,
    List<RecommendationReasonResponse> reasons,
    String analysisContext
) {
}
