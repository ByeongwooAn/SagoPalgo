package com.sagopalgo.api.recommendation.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.jsonPath;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;

import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import com.sagopalgo.api.recommendation.dto.DailyInference;
import java.math.BigDecimal;
import java.util.List;
import java.time.LocalDateTime;
import java.time.LocalDate;
import java.net.SocketTimeoutException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

@ExtendWith(OutputCaptureExtension.class)
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
            .andExpect(jsonPath("$.candles[0].dateTime").value("2026-09-15T00:00:00"))
            .andExpect(jsonPath("$.candles[1].dateTime").value("2026-09-16T12:34:56.123"))
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
    void dailyInferenceSendsDateOnlyAndMapsUnroundedProbability() {
        LocalDate date = LocalDate.of(2026, 10, 30);
        server.expect(requestTo("http://ai.test/internal/ai/infer-daily"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(jsonPath("$.priceBasis").value("RAW"))
            .andExpect(jsonPath("$.bars[0].businessDate").value("2026-10-30"))
            .andRespond(withSuccess("""
                {"stockCode":"000660","signalDate":"2026-10-30","modelVersion":"daily-l2-logistic-v1",
                 "modelSha256":"hash","probability":0.56789123456789,"threshold":0.5,"contributions":{"openToClose":0.1}}
                """, MediaType.APPLICATION_JSON));
        var request = new DailyInference.Request("000660", "KOSPI", "KIS", "RAW", date,
            List.of(new DailyInference.Bar(date, BigDecimal.TEN, BigDecimal.TEN, BigDecimal.ONE, BigDecimal.TEN, BigDecimal.TEN)));
        var result = client.inferDaily(request).orElseThrow();
        assertThat(result.signalDate()).isEqualTo(date);
        assertThat(result.probability()).isEqualTo(0.56789123456789);
        assertThat(result.contributions()).containsEntry("openToClose", 0.1);
        server.verify();
    }

    @Test
    @DisplayName("AI 서버가 비활성이면 외부 요청 없이 빈 결과를 반환한다")
    void analyzeSkipsDisabledServer() {
        properties.setEnabled(false);

        assertThat(client.analyze(request())).isEmpty();
        server.verify();
    }

    @Test
    void validationFailureKeepsFallbackButDoesNotDumpUpstreamInputs(CapturedOutput output) {
        server.expect(requestTo("http://ai.test/internal/ai/analyze-investment"))
            .andRespond(withStatus(HttpStatus.UNPROCESSABLE_ENTITY).contentType(MediaType.APPLICATION_JSON)
                .body("{\"detail\":\"private-ai-payload\"}"));
        assertThat(client.analyze(request())).isEmpty();
        assertThat(output.getOut()).contains("httpStatus=422").doesNotContain("private-ai-payload");
        server.verify();
    }

    @Test
    void transportFailureKeepsFallbackWithoutExceptionText(CapturedOutput output) {
        server.expect(requestTo("http://ai.test/internal/ai/analyze-investment"))
            .andRespond(withException(new SocketTimeoutException("private-ai-url")));
        assertThat(client.analyze(request())).isEmpty();
        assertThat(output.getOut()).contains("type=ResourceAccessException").doesNotContain("private-ai-url");
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
            List.of(
                new AiInvestmentAnalysisRequest.CandleInput(LocalDateTime.of(2026, 9, 15, 0, 0),
                    new BigDecimal("74000"), new BigDecimal("1000")),
                new AiInvestmentAnalysisRequest.CandleInput(LocalDateTime.of(2026, 9, 16, 12, 34, 56, 123000000),
                    new BigDecimal("75200"), new BigDecimal("1200"))
            ),
            List.of(),
            List.of(),
            "HOLDING",
            null,
            null,
            null
        );
    }
}
