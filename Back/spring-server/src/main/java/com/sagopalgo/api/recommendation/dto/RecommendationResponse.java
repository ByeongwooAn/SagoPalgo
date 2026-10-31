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
    String analysisContext,
    AnalysisEvidence evidence
) {
    public RecommendationResponse(Long id, String code, String name, String market, String type,
        String status, String label, int score, BigDecimal price, BigDecimal stop, BigDecimal take,
        String summary, LocalDateTime at, List<RecommendationReasonResponse> reasons, String context) {
        this(id, code, name, market, type, status, label, score, price, stop, take, summary, at, reasons, context, null);
    }
}
