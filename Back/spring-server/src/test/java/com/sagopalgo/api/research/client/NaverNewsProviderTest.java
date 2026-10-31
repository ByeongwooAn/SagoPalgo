package com.sagopalgo.api.research.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;

import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.time.LocalDate;
import java.util.List;
import java.net.UnknownHostException;
import java.net.SocketTimeoutException;
import java.net.ConnectException;
import javax.net.ssl.SSLHandshakeException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.ResourceAccessException;

class NaverNewsProviderTest {

    private MockRestServiceServer server;
    private NaverNewsProvider provider;

    @BeforeEach
    void setUp() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        properties.getNaverNews().setEnabled(true);
        properties.getNaverNews().setBaseUrl("https://naver.test");
        properties.getNaverNews().setClientId("client-id");
        properties.getNaverNews().setClientSecret("client-secret");
        properties.getNaverNews().setDisplay(5);

        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        provider = new NaverNewsProvider(properties, builder.build());
    }

    @Test
    @DisplayName("네이버 뉴스 응답의 HTML을 제거하고 내부 모델로 정규화한다")
    void searchNormalizesNewsArticles() {
        server.expect(requestTo("https://naver.test/search/v1/news?query=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&display=5&start=1&sort=date&format=json"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-NCP-APIGW-API-KEY-ID", "client-id"))
            .andExpect(header("X-NCP-APIGW-API-KEY", "client-secret"))
            .andExpect(request -> assertThat(request.getHeaders()).doesNotContainKeys("X-Naver-Client-Id", "X-Naver-Client-Secret"))
            .andRespond(withSuccess("""
                {
                  "items": [
                    {
                      "title": "<b>삼성전자</b> 신규 투자",
                      "originallink": "https://news.example/article-1",
                      "link": "https://n.news.naver.com/article-1",
                      "description": "AI &amp; 반도체 <b>투자</b> 확대",
                      "pubDate": "Sun, 21 Sep 2025 10:00:00 +0900"
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        List<NewsArticle> articles = provider.search(new ResearchRequest(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        ));

        assertThat(articles).hasSize(1);
        assertThat(articles.get(0).provider()).isEqualTo("NAVER_NEWS");
        assertThat(articles.get(0).title()).isEqualTo("삼성전자 신규 투자");
        assertThat(articles.get(0).summary()).isEqualTo("AI & 반도체 투자 확대");
        assertThat(articles.get(0).link()).isEqualTo("https://news.example/article-1");
        server.verify();
    }

    @Test
    void forbiddenExplainsSearchPermissionAndKeepsOnlySafeStatusAndCode() {
        expectFailure(HttpStatus.FORBIDDEN, "{\"errorCode\":\"024\",\"errorMessage\":\"private-secret client-id\"}");
        assertThatThrownBy(() -> provider.search(request()))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("stage=NEWS_SEARCH httpStatus=403 naverCode=024")
            .hasMessageContaining("검색 API 사용 권한")
            .hasMessageNotContaining("private-secret").hasMessageNotContaining("client-id")
            .hasMessageNotContaining("https://");
        server.verify();
    }

    @Test
    void unauthorizedExplainsCredentialsWithoutReturningUpstreamMessage() {
        expectFailure(HttpStatus.UNAUTHORIZED, "{\"errorCode\":\"024\",\"errorMessage\":\"private-secret\"}");
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=401").hasMessageContaining("Client ID/Secret")
            .hasMessageNotContaining("private-secret");
        server.verify();
    }

    @Test
    void requestLimitIsNotReportedAsAnAuthenticationError() {
        expectFailure(HttpStatus.TOO_MANY_REQUESTS, "{\"errorCode\":\"012\",\"errorMessage\":\"private-secret\"}");
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=429 naverCode=012").hasMessageContaining("호출 한도")
            .hasMessageNotContaining("private-secret");
        server.verify();
    }

    @Test
    void searchSpecificErrorCodeIsPreservedWithoutRawMessage() {
        expectFailure(HttpStatus.BAD_REQUEST, "{\"errorCode\":\"SE06\",\"errorMessage\":\"private-secret\"}");
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=400 naverCode=SE06").hasMessageNotContaining("private-secret");
        server.verify();
    }

    @Test
    void malformedOrUnexpectedCodesAreNotCopiedToDiagnostics() {
        expectFailure(HttpStatus.BAD_GATEWAY, "{\"errorCode\":\"private-secret\\nforged log\",\"errorMessage\":\"client-id\"}");
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=502 naverCode=UNAVAILABLE")
            .hasMessageNotContaining("private-secret").hasMessageNotContaining("forged log")
            .hasMessageNotContaining("client-id");
        server.verify();
    }

    @Test
    void nonJsonErrorBodyIsNotReturnedAsProviderStatus() {
        expectFailure(HttpStatus.BAD_GATEWAY, "<html>private-secret</html>");
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=502 naverCode=UNAVAILABLE")
            .hasMessageNotContaining("private-secret");
        server.verify();
    }

    @Test
    void timeoutIsReportedWithoutItsCauseText() {
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("/search/v1/news"))
            .andRespond(withException(new SocketTimeoutException("private-secret")));
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("kind=TIMEOUT").hasMessageNotContaining("private-secret");
        server.verify();
    }

    @Test
    void networkFailuresUseFixedTypesAndDoNotKeepSensitiveCauses() {
        List<java.io.IOException> causes = List.of(new UnknownHostException("private-host"),
            new SSLHandshakeException("private-certificate"), new ConnectException("private-host"));
        List<String> kinds = List.of("DNS", "TLS", "CONNECT");
        for (int index = 0; index < causes.size(); index++) {
            var failure = NaverNewsErrors.requestFailure(new ResourceAccessException("private-url", causes.get(index)));
            assertThat(failure.getMessage()).contains("kind=" + kinds.get(index))
                .doesNotContain("private-host", "private-url", "private-certificate");
            assertThat(failure.getErrorCode()).isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
            assertThat(failure.getCause()).isNull();
        }
    }

    @Test
    void successfulEmptyItemsAreNotAFailure() {
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("/search/v1/news"))
            .andRespond(withSuccess("{\"items\":[]}", MediaType.APPLICATION_JSON));
        assertThat(provider.search(request())).isEmpty();
        server.verify();
    }

    private void expectFailure(HttpStatus status, String body) {
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("/search/v1/news"))
            .andRespond(withStatus(status).contentType(MediaType.APPLICATION_JSON).body(body));
    }

    @Test
    void cloudDefaultsUseOfficialApiHubHostPathAndAuthenticationHeaders() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        properties.getNaverNews().setEnabled(true);
        properties.getNaverNews().setClientId("cloud-client-id");
        properties.getNaverNews().setClientSecret("cloud-client-secret");
        RestClient.Builder builder = RestClient.builder();
        var cloudServer = MockRestServiceServer.bindTo(builder).build();
        cloudServer.expect(request -> {
            assertThat(request.getURI().getScheme()).isEqualTo("https");
            assertThat(request.getURI().getHost()).isEqualTo("naverapihub.apigw.ntruss.com");
            assertThat(request.getURI().getPath()).isEqualTo("/search/v1/news");
            assertThat(request.getURI().getRawQuery()).contains("format=json", "display=10", "sort=date");
        })
            .andExpect(header("X-NCP-APIGW-API-KEY-ID", "cloud-client-id"))
            .andExpect(header("X-NCP-APIGW-API-KEY", "cloud-client-secret"))
            .andRespond(withSuccess("{\"items\":[]}", MediaType.APPLICATION_JSON));
        assertThat(new NaverNewsProvider(properties, builder.build()).search(request())).isEmpty();
        cloudServer.verify();
    }

    @Test
    void cloudGatewayNestedErrorRetainsCodeButNotMessageOrDetails() {
        expectFailure(HttpStatus.UNAUTHORIZED, """
            {"error":{"errorCode":"200","message":"private-client-secret","details":"private-client-id"}}
            """);
        assertThatThrownBy(() -> provider.search(request()))
            .hasMessageContaining("httpStatus=401 naverCode=200")
            .hasMessageContaining("NAVER API HUB Application")
            .hasMessageNotContaining("private-client-secret").hasMessageNotContaining("private-client-id");
        server.verify();
    }

    private ResearchRequest request() {
        return new ResearchRequest("000660", "SK하이닉스", LocalDate.of(2026, 10, 1), LocalDate.of(2026, 10, 31));
    }
}
