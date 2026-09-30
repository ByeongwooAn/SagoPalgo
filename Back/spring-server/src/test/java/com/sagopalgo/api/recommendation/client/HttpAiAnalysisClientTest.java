package com.sagopalgo.api.recommendation.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

class HttpAiAnalysisClientTest {

    private MockRestServiceServer server;
    private AiAnalysisProperties properties;
    private HttpAiAnalysisClient client;

    @BeforeEach
    void setUp() {
        properties = new AiAnalysisProperties();
        properties.setEnabled(true);
        properties.setBaseUrl("http://ai.test");
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        client = new HttpAiAnalysisClient(builder.build(), properties);
    }

    @Test
    @DisplayName("Python 분석 서버의 추천과 점수 근거를 역직렬화한다")
    void analyzeMapsPythonResponse() {
        server.expect(requestTo("http://ai.test/internal/ai/analyze-investment"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess("""
                {
                  "modelVersion": "WEIGHTED_SIGNAL_V1",
                  "recommendationType": "BUY",
                  "status": "BUY_WATCH",
                  "score": 67,
                  "summary": "긍정 신호가 우세합니다.",
                  "reasons": [
                    {
                      "label": "가격 추세",
                      "description": "종가가 상승했습니다.",
                      "type": "PRICE",
                      "score": 12
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        AiInvestmentAnalysisResponse response = client.analyze(request()).orElseThrow();

        assertThat(response.modelVersion()).isEqualTo("WEIGHTED_SIGNAL_V1");
        assertThat(response.status()).isEqualTo("BUY_WATCH");
        assertThat(response.reasons()).extracting(AiInvestmentAnalysisResponse.Reason::type)
            .containsExactly("PRICE");
        server.verify();
    }

    @Test
    @DisplayName("AI 서버가 비활성이면 외부 요청 없이 빈 결과를 반환한다")
    void analyzeSkipsDisabledServer() {
        properties.setEnabled(false);

        assertThat(client.analyze(request())).isEmpty();
        server.verify();
    }

    private AiInvestmentAnalysisRequest request() {
        return new AiInvestmentAnalysisRequest(
            "005930",
            "삼성전자",
            "KOSPI",
            new BigDecimal("75200"),
            new BigDecimal("70000"),
            new BigDecimal("7.43"),
            new BigDecimal("-5"),
            new BigDecimal("12"),
            List.of(),
            List.of(),
            List.of(),
            "HOLDING",
            null,
            null,
            null
        );
    }
}
