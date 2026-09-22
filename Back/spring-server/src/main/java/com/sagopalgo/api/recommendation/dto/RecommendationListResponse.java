package com.sagopalgo.api.recommendation.dto;

import java.util.List;

/**
 * 사용자 추천 이력의 페이지 응답입니다.
 */
public record RecommendationListResponse(
    List<RecommendationResponse> items,
    int page,
    int size,
    long total
) {
}
