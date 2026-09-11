package com.sagopalgo.api.dashboard.dto;

/**
 * 대시보드 대표 추천의 설명 근거 DTO입니다.
 */
public record DashboardRecommendationReasonResponse(
    String label,
    String description,
    String type,
    int score
) {
}
