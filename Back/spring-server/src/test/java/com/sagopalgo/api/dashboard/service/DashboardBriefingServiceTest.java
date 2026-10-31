package com.sagopalgo.api.dashboard.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.research.mapper.ResearchNewsMapper;
import com.sagopalgo.api.research.model.ResearchNewsRecord;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DataAccessResourceFailureException;

class DashboardBriefingServiceTest {
    private final ResearchNewsMapper mapper = mock(ResearchNewsMapper.class);
    private final DashboardBriefingService service = new DashboardBriefingService(mock(KisMarketPriceClient.class), mapper);

    @Test
    void classifiesPerArticleAndDeduplicatesSameProviderLinkAcrossStocks() {
        when(mapper.findRecentForUser(eq(1L), any(), any())).thenReturn(List.of(
            article("수주 확대", "a"), article("수주 확대", "a"),
            article("적자 발표", "b"), article("수주 확대에도 적자", "c"), article("정기 주총", "d")));
        var result = service.news(1L);
        assertThat(result.articleCount()).isEqualTo(4);
        assertThat(result.positiveCount()).isEqualTo(1);
        assertThat(result.negativeCount()).isEqualTo(1);
        assertThat(result.label()).isEqualTo("중립");
        assertThat(result.method()).contains("키워드", "7일", "200");
        assertThat(result.latestPublishedAt()).isEqualTo(Instant.parse("2026-10-30T01:00:00Z"));
    }

    @Test
    void noCollectedArticlesIsNotNeutralSentiment() {
        when(mapper.findRecentForUser(eq(1L), any(), any())).thenReturn(List.of());
        var result = service.news(1L);
        assertThat(result.status()).isEqualTo("EMPTY");
        assertThat(result.label()).isEqualTo("저장 뉴스 없음");
        assertThat(result.latestPublishedAt()).isNull();
    }

    @Test
    void storageFailureIsNotAnEmptySuccessfulResult() {
        when(mapper.findRecentForUser(eq(1L), any(), any())).thenThrow(new DataAccessResourceFailureException("private DB message"));
        var result = service.news(1L);
        assertThat(result.status()).isEqualTo("FAILED");
        assertThat(result.toString()).doesNotContain("private DB message");
    }

    private ResearchNewsRecord article(String title, String link) {
        var article = new ResearchNewsRecord();
        article.setProvider("NAVER"); article.setTitle(title); article.setLink(link);
        article.setPublishedAt(Instant.parse("2026-10-30T01:00:00Z"));
        return article;
    }
}
