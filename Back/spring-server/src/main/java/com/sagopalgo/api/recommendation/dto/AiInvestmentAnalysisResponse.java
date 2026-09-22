package com.sagopalgo.api.recommendation.dto;

import java.util.List;

/**
 * Python 분석 서버가 반환하는 설명 가능한 종합 추천입니다.
 */
public record AiInvestmentAnalysisResponse(
    String modelVersion,
    String recommendationType,
    String status,
    int score,
    String summary,
    List<Reason> reasons
) {
    public record Reason(
        String label,
        String description,
        String type,
        int score
    ) {
    }
}
