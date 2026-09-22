package com.sagopalgo.api.recommendation.client;

import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import java.util.Optional;

/**
 * 추천 서비스가 실제 분석 구현 방식과 분리되도록 하는 AI 서버 경계입니다.
 */
public interface AiAnalysisGateway {

    Optional<AiInvestmentAnalysisResponse> analyze(AiInvestmentAnalysisRequest request);
}
