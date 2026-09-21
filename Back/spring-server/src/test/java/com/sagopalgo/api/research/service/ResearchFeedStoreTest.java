package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.research.mapper.ResearchDisclosureMapper;
import com.sagopalgo.api.research.mapper.ResearchNewsMapper;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchDisclosureRecord;
import com.sagopalgo.api.research.model.ResearchNewsRecord;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class ResearchFeedStoreTest {

    @Test
    @DisplayName("반복 수집된 뉴스와 공시는 같은 중복 제거 키로 upsert한다")
    void saveAndFindUsesStableDeduplicationKeys() {
        ResearchNewsMapper newsMapper = mock(ResearchNewsMapper.class);
        ResearchDisclosureMapper disclosureMapper = mock(ResearchDisclosureMapper.class);
        ResearchFeedStore store = new ResearchFeedStore(newsMapper, disclosureMapper);
        ResearchRequest request = request("005930");
        NewsArticle article = article("005930");
        Disclosure disclosure = disclosure("005930");
        when(newsMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());
        when(disclosureMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());

        store.saveAndFind(request, List.of(article, article), List.of(disclosure, disclosure));

        ArgumentCaptor<ResearchNewsRecord> newsCaptor = ArgumentCaptor.forClass(ResearchNewsRecord.class);
        verify(newsMapper, times(2)).upsert(newsCaptor.capture());
        assertThat(newsCaptor.getAllValues())
            .extracting(ResearchNewsRecord::getContentKey)
            .containsExactly(
                newsCaptor.getAllValues().get(0).getContentKey(),
                newsCaptor.getAllValues().get(0).getContentKey()
            );
        verify(disclosureMapper, times(2)).upsert(any(ResearchDisclosureRecord.class));
    }

    @Test
    @DisplayName("같은 기사라도 연결 종목이 다르면 별도 뉴스 키를 사용한다")
    void saveAndFindSeparatesNewsByStockCode() {
        ResearchNewsMapper newsMapper = mock(ResearchNewsMapper.class);
        ResearchDisclosureMapper disclosureMapper = mock(ResearchDisclosureMapper.class);
        ResearchFeedStore store = new ResearchFeedStore(newsMapper, disclosureMapper);
        when(newsMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());
        when(disclosureMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());

        store.saveAndFind(request("005930"), List.of(article("005930")), List.of());
        store.saveAndFind(request("000660"), List.of(article("000660")), List.of());

        ArgumentCaptor<ResearchNewsRecord> captor = ArgumentCaptor.forClass(ResearchNewsRecord.class);
        verify(newsMapper, times(2)).upsert(captor.capture());
        assertThat(captor.getAllValues().get(0).getContentKey())
            .isNotEqualTo(captor.getAllValues().get(1).getContentKey());
    }

    @Test
    @DisplayName("식별 정보가 없는 외부 응답은 저장하지 않는다")
    void saveAndFindSkipsItemsWithoutIdentity() {
        ResearchNewsMapper newsMapper = mock(ResearchNewsMapper.class);
        ResearchDisclosureMapper disclosureMapper = mock(ResearchDisclosureMapper.class);
        ResearchFeedStore store = new ResearchFeedStore(newsMapper, disclosureMapper);
        NewsArticle emptyArticle = new NewsArticle(
            "NAVER_NEWS",
            "005930",
            " ",
            " ",
            "기사 요약",
            Instant.parse("2025-09-21T01:00:00Z")
        );
        Disclosure emptyDisclosure = new Disclosure(
            "OPEN_DART",
            "005930",
            "00126380",
            "삼성전자",
            "주요사항보고서",
            " ",
            "삼성전자",
            LocalDate.of(2025, 9, 21),
            "https://dart.test/report"
        );
        when(newsMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());
        when(disclosureMapper.findByStockCodeAndDateRange(any(), any(), any())).thenReturn(List.of());

        store.saveAndFind(request("005930"), List.of(emptyArticle), List.of(emptyDisclosure));

        verify(newsMapper).findByStockCodeAndDateRange(any(), any(), any());
        verify(disclosureMapper).findByStockCodeAndDateRange(any(), any(), any());
        verify(newsMapper, never()).upsert(any(ResearchNewsRecord.class));
        verify(disclosureMapper, never()).upsert(any(ResearchDisclosureRecord.class));
    }

    private ResearchRequest request(String stockCode) {
        return new ResearchRequest(
            stockCode,
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );
    }

    private NewsArticle article(String stockCode) {
        return new NewsArticle(
            "NAVER_NEWS",
            stockCode,
            "반도체 투자 확대",
            "https://news.test/article-1",
            "기사 요약",
            Instant.parse("2025-09-21T01:00:00Z")
        );
    }

    private Disclosure disclosure(String stockCode) {
        return new Disclosure(
            "OPEN_DART",
            stockCode,
            "00126380",
            "삼성전자",
            "주요사항보고서",
            "20250921000123",
            "삼성전자",
            LocalDate.of(2025, 9, 21),
            "https://dart.test/report"
        );
    }
}
