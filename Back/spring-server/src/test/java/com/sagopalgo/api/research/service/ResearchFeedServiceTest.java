package com.sagopalgo.api.research.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.provider.DisclosureProvider;
import com.sagopalgo.api.research.provider.NewsProvider;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ResearchFeedServiceTest {

    @Test
    @DisplayName("뉴스 조회가 실패해도 공시 결과와 Provider 상태를 반환한다")
    void getFeedKeepsPartialResultWhenOneProviderFails() {
        ResearchProviderProperties properties = new ResearchProviderProperties();
        ResearchFeedService service = new ResearchFeedService(
            List.of(new FailingNewsProvider()),
            List.of(new FixtureDisclosureProvider()),
            properties
        );

        ResearchFeedResponse response = service.getFeed(
            "005930",
            "삼성전자",
            LocalDate.of(2025, 9, 1),
            LocalDate.of(2025, 9, 30)
        );

        assertThat(response.news()).isEmpty();
        assertThat(response.disclosures()).hasSize(1);
        assertThat(response.providers())
            .extracting("provider", "status")
            .containsExactly(
                org.assertj.core.groups.Tuple.tuple("NEWS_TEST", "FAILED"),
                org.assertj.core.groups.Tuple.tuple("DART_TEST", "SUCCESS")
            );
    }

    @Test
    @DisplayName("조회 시작일이 종료일보다 늦으면 검증 오류를 반환한다")
    void getFeedRejectsInvalidDateRange() {
        ResearchFeedService service = new ResearchFeedService(List.of(), List.of(), new ResearchProviderProperties());

        assertThatThrownBy(() -> service.getFeed(
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
