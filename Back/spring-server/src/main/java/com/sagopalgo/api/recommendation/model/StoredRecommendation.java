package com.sagopalgo.api.recommendation.model;

import java.util.List;

/**
 * 저장된 추천 본문과 점수 근거를 묶은 조회 결과입니다.
 */
public record StoredRecommendation(
    RecommendationRecord recommendation,
    List<RecommendationReasonRecord> reasons
) {
}
