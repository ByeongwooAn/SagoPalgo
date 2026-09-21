package com.sagopalgo.api.research.service;

import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.dto.ResearchProviderStatusResponse;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ResearchSyncServiceTest {

    @Test
    @DisplayName("Provider 일부 실패는 PARTIAL 상태로 저장한다")
    void syncStoresPartialStatus() {
        ResearchFeedService feedService = mock(ResearchFeedService.class);
        ResearchSyncStatusStore statusStore = mock(ResearchSyncStatusStore.class);
        ResearchSyncService service = new ResearchSyncService(
            feedService,
            statusStore,
            new ResearchProviderProperties()
        );
        ResearchFeedResponse response = new ResearchFeedResponse(
            "005930",
            "삼성전자",
            LocalDate.of(2026, 9, 1),
            LocalDate.of(2026, 9, 22),
            List.of(),
            List.of(),
            List.of(
                new ResearchProviderStatusResponse("NAVER_NEWS", "NEWS", "SUCCESS", "1건 조회"),
                new ResearchProviderStatusResponse("OPEN_DART", "DISCLOSURE", "FAILED", "조회 실패")
            )
        );
        when(feedService.syncFeed("005930", "삼성전자", null, null)).thenReturn(response);

        service.sync(1L, "005930", "삼성전자", null, null, ResearchSyncService.SCHEDULED);

        verify(statusStore).save(
            eq(1L),
            eq("005930"),
            eq("삼성전자"),
            eq("SCHEDULED"),
            eq("PARTIAL"),
            eq(0),
            eq(0),
            eq(1),
            eq(1),
            eq(0),
            eq("Provider 성공 1 · 실패 1 · 비활성 0")
        );
    }

    @Test
    @DisplayName("동기화 예외는 FAILED 상태로 기록하고 다시 전달한다")
    void syncStoresFailureAndRethrows() {
        ResearchFeedService feedService = mock(ResearchFeedService.class);
        ResearchSyncStatusStore statusStore = mock(ResearchSyncStatusStore.class);
        ResearchSyncService service = new ResearchSyncService(
            feedService,
            statusStore,
            new ResearchProviderProperties()
        );
        IllegalStateException failure = new IllegalStateException("저장 실패");
        when(feedService.syncFeed("005930", "삼성전자", null, null)).thenThrow(failure);

        org.assertj.core.api.Assertions.assertThatThrownBy(
            () -> service.sync(1L, "005930", "삼성전자", null, null, ResearchSyncService.MANUAL)
        ).isSameAs(failure);

        verify(statusStore).save(
            eq(1L),
            eq("005930"),
            eq("삼성전자"),
            eq("MANUAL"),
            eq("FAILED"),
            eq(0),
            eq(0),
            eq(0),
            eq(1),
            eq(0),
            eq("저장 실패")
        );
    }
}
