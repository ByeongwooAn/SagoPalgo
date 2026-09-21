package com.sagopalgo.api.research.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

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
        server.expect(requestTo("https://naver.test/v1/search/news.json?query=%EC%82%BC%EC%84%B1%EC%A0%84%EC%9E%90&display=5&start=1&sort=date"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header("X-Naver-Client-Id", "client-id"))
            .andExpect(header("X-Naver-Client-Secret", "client-secret"))
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
}
