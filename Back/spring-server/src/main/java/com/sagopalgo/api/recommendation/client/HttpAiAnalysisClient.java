package com.sagopalgo.api.recommendation.client;

import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

/**
 * 로컬 Python 분석 서버를 호출하며, 장애 시 규칙 엔진 fallback을 위해 빈 결과를 반환합니다.
 */
@Component
public class HttpAiAnalysisClient implements AiAnalysisGateway {

    private static final Logger log = LoggerFactory.getLogger(HttpAiAnalysisClient.class);

    private final RestClient restClient;
    private final AiAnalysisProperties properties;

    public HttpAiAnalysisClient(RestClient restClient, AiAnalysisProperties properties) {
        this.restClient = restClient;
        this.properties = properties;
    }

    @Override
    public Optional<AiInvestmentAnalysisResponse> analyze(AiInvestmentAnalysisRequest request) {
        if (!properties.isEnabled()) {
            return Optional.empty();
        }
        try {
            AiInvestmentAnalysisResponse response = restClient.post()
                .uri(properties.getBaseUrl() + properties.getAnalysisPath())
                .body(request)
                .retrieve()
                .body(AiInvestmentAnalysisResponse.class);
            return Optional.ofNullable(response);
        } catch (RuntimeException exception) {
            String diagnostic = exception instanceof RestClientResponseException response
                ? "httpStatus=" + response.getStatusCode().value()
                : "type=" + exception.getClass().getSimpleName();
            log.warn(
                "AI 분석 서버 호출 실패. stockCode={} {}",
                request.stockCode(),
                diagnostic
            );
            return Optional.empty();
        }
    }
}
