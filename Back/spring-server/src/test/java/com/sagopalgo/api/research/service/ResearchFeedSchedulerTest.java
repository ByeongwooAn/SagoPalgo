package com.sagopalgo.api.research.service;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.watchlist.dto.WatchlistResponse;
import com.sagopalgo.api.watchlist.service.WatchlistService;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class ResearchFeedSchedulerTest {

    @Test
    @DisplayName("한 관심 종목이 실패해도 다음 종목 동기화를 계속한다")
    void syncWatchlistContinuesAfterItemFailure() {
        WatchlistService watchlistService = mock(WatchlistService.class);
        ResearchSyncService researchSyncService = mock(ResearchSyncService.class);
        PersonalModeProperties personal = new PersonalModeProperties(true, 1L, "개인 사용자", "local@test");
        ResearchFeedScheduler scheduler = new ResearchFeedScheduler(
            watchlistService,
            researchSyncService,
            personal
        );
        WatchlistResponse first = item(1L, "005930", "삼성전자");
        WatchlistResponse second = item(2L, "000660", "SK하이닉스");
        when(watchlistService.findAll(1L)).thenReturn(List.of(first, second));
        when(researchSyncService.sync(
            eq(1L), eq("005930"), eq("삼성전자"), any(), any(), eq("SCHEDULED")
        )).thenThrow(new IllegalStateException("첫 종목 실패"));

        scheduler.syncWatchlist();

        verify(researchSyncService, times(2)).sync(
            eq(1L), any(), any(), any(), any(), eq("SCHEDULED")
        );
        verify(researchSyncService).sync(
            eq(1L), eq("000660"), eq("SK하이닉스"), any(), any(), eq("SCHEDULED")
        );
    }

    private WatchlistResponse item(Long id, String stockCode, String stockName) {
        return new WatchlistResponse(id, stockCode, stockName, "KOSPI", true, Instant.now());
    }
}
