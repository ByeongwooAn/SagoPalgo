package com.sagopalgo.api.recommendation.dto;

/**
 * 저장된 추천 점수의 개별 산출 근거입니다.
 */
public record RecommendationReasonResponse(
    String type,
    String label,
    String description,
    int score
) {
}
