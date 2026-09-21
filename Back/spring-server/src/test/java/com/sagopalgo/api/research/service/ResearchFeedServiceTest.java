package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import com.sagopalgo.api.research.provider.DisclosureProvider;
import com.sagopalgo.api.research.provider.NewsProvider;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ResearchFeedServiceTest {

    @Test
    @DisplayName("뉴스 조회가 실패해도 공시 결과와 Provider 상태를 반환한다")
    void syncFeedKeepsPartialResultWhenOneProviderFails() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        ResearchFeedStore store = mock(ResearchFeedStore.class);
        ResearchFeedService service = new ResearchFeedService(
            List.of(new FailingNewsProvider()),
            List.of(new FixtureDisclosureProvider()),
            properties,
            store
        );
        ResearchRequest request = new ResearchRequest(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );
        when(store.saveAndFind(eq(request), anyList(), anyList())).thenAnswer(invocation -> new StoredResearchFeed(
            invocation.getArgument(1),
            invocation.getArgument(2)
        ));

        ResearchFeedResponse response = service.syncFeed(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );

        assertThat(response.news()).isEmpty();
        assertThat(response.disclosures()).hasSize(1);
        verify(store).saveAndFind(eq(request), anyList(), anyList());
        assertThat(response.providers())
            .extracting("provider", "status")
            .containsExactly(
                org.assertj.core.groups.Tuple.tuple("NEWS_TEST", "FAILED"),
                org.assertj.core.groups.Tuple.tuple("DART_TEST", "SUCCESS")
            );
    }

    @Test
    @DisplayName("저장 조회는 외부 Provider를 호출하지 않고 로컬 DB 결과만 반환한다")
    void getStoredFeedReturnsLocalData() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        NewsProvider newsProvider = mock(NewsProvider.class);
        DisclosureProvider disclosureProvider = mock(DisclosureProvider.class);
        ResearchFeedStore store = mock(ResearchFeedStore.class);
        ResearchFeedService service = new ResearchFeedService(
            List.of(newsProvider),
            List.of(disclosureProvider),
            properties,
            store
        );
        ResearchRequest request = new ResearchRequest(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );
        when(store.find(request)).thenReturn(new StoredResearchFeed(
            List.of(new NewsArticle(
                "NAVER_NEWS",
                "005930",
                "저장된 뉴스",
                "https://news.test/1",
                "요약",
                null
            )),
            List.of()
        ));

        ResearchFeedResponse response = service.getStoredFeed(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );

        assertThat(response.news()).extracting(NewsArticle::title).containsExactly("저장된 뉴스");
        assertThat(response.providers())
            .extracting("provider", "dataType", "status")
            .containsExactly(org.assertj.core.groups.Tuple.tuple("LOCAL_DB", "CACHE", "SUCCESS"));
        verify(store).find(request);
    }

    @Test
    @DisplayName("조회 시작일이 종료일보다 늦으면 검증 오류를 반환한다")
    void getFeedRejectsInvalidDateRange() {
        ResearchFeedService service = new ResearchFeedService(
            List.of(),
            List.of(),
            new ResearchProviderProperties(),
            mock(ResearchFeedStore.class)
        );

        assertThatThrownBy(() -> service.getStoredFeed(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 30),
            LocalDate.of(2025, 9, 1)
        ))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.VALIDATION_ERROR);
    }

    private static class FailingNewsProvider implements NewsProvider {

        @Override
        public String providerCode() {
            return "NEWS_TEST";
        }

        @Override
        public boolean supports(ResearchRequest request) {
            return true;
        }

        @Override
        public List<NewsArticle> search(ResearchRequest request) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "뉴스 테스트 실패");
        }
    }

    private static class FixtureDisclosureProvider implements DisclosureProvider {

        @Override
        public String providerCode() {
            return "DART_TEST";
        }

        @Override
        public boolean supports(ResearchRequest request) {
            return true;
        }

        @Override
        public List<Disclosure> search(ResearchRequest request) {
            return List.of(new Disclosure(
                "DART_TEST",
                request.stockCode(),
                "00126380",
                request.stockName(),
                "주요사항보고서",
                "20250921000123",
                request.stockName(),
                LocalDate.of(2025, 9, 21),
                "https://dart.test/report"
            ));
        }
    }
}
