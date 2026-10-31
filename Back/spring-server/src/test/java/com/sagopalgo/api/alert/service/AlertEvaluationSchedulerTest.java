package com.sagopalgo.api.alert.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.alert.model.PortfolioPosition;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.mockito.Mockito;

class AlertEvaluationSchedulerTest {

    @Test
    @DisplayName("종목별 시세 평가 결과를 모아 포트폴리오 위험을 한 번 평가한다")
    void evaluatesPortfolioWithFetchedQuotes() {
        HoldingService holdingService = Mockito.mock(HoldingService.class);
        RecommendationService recommendationService = Mockito.mock(RecommendationService.class);
        MarketPriceService marketPriceService = Mockito.mock(MarketPriceService.class);
        EventAlertService eventAlertService = Mockito.mock(EventAlertService.class);
        PortfolioRiskAlertService portfolioRiskAlertService = Mockito.mock(PortfolioRiskAlertService.class);
        var watchlists = Mockito.mock(com.sagopalgo.api.watchlist.mapper.WatchlistMapper.class);
        AlertEvaluationScheduler scheduler = new AlertEvaluationScheduler(
            holdingService,
            recommendationService,
            marketPriceService,
            eventAlertService,
            portfolioRiskAlertService,
            new PersonalModeProperties(true, 1L, "개인 사용자", "local@sagopalgo.local"),
            watchlists
        );
        Holding holding = holding();
        StockQuote quote = quote();
        when(holdingService.findActiveIds(1L)).thenReturn(List.of(7L));
        when(holdingService.findRecord(1L, 7L)).thenReturn(holding);
        when(marketPriceService.quote(holding)).thenReturn(quote);
        var owned = new com.sagopalgo.api.watchlist.model.WatchlistItem();
        owned.setWatchlistId(12L); owned.setStockCode("005930"); owned.setMarket("KOSPI"); owned.setAlertEnabled(true);
        when(watchlists.findAllByUserId(1L)).thenReturn(List.of(owned));

        scheduler.analyzeHoldings();

        verify(eventAlertService).createPriceAlerts(holding, quote);
        verify(recommendationService).analyzeHolding(1L, 7L);
        verify(recommendationService, Mockito.never()).analyzeWatchlist(1L, 12L);
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<PortfolioPosition>> captor = ArgumentCaptor.forClass(List.class);
        verify(portfolioRiskAlertService).createAlerts(org.mockito.ArgumentMatchers.eq(1L), captor.capture());
        assertThat(captor.getValue()).containsExactly(new PortfolioPosition(holding, quote));
    }

    @Test
    void enabledWatchlistsAreAnalyzedIndependentlyAndOneFailureDoesNotBlockTheNext() {
        var holdings = Mockito.mock(HoldingService.class);
        var recommendations = Mockito.mock(RecommendationService.class);
        var watchlists = Mockito.mock(com.sagopalgo.api.watchlist.mapper.WatchlistMapper.class);
        var first = new com.sagopalgo.api.watchlist.model.WatchlistItem(); first.setWatchlistId(11L); first.setAlertEnabled(true);
        var second = new com.sagopalgo.api.watchlist.model.WatchlistItem(); second.setWatchlistId(12L); second.setAlertEnabled(true);
        first.setStockCode("005930"); first.setMarket("KOSPI");
        second.setStockCode("000660"); second.setMarket("KOSPI");
        var disabled = new com.sagopalgo.api.watchlist.model.WatchlistItem(); disabled.setWatchlistId(13L); disabled.setAlertEnabled(false);
        when(watchlists.findAllByUserId(1L)).thenReturn(List.of(first, second, disabled));
        when(recommendations.analyzeWatchlist(1L, 11L)).thenThrow(new IllegalStateException("price unavailable"));
        var scheduler = new AlertEvaluationScheduler(holdings, recommendations, Mockito.mock(MarketPriceService.class),
            Mockito.mock(EventAlertService.class), Mockito.mock(PortfolioRiskAlertService.class),
            new PersonalModeProperties(true, 1L, "사용자", "local@test.local"), watchlists);
        scheduler.analyzeHoldings();
        verify(recommendations).analyzeWatchlist(1L, 11L);
        verify(recommendations).analyzeWatchlist(1L, 12L);
        verify(recommendations, Mockito.never()).analyzeWatchlist(1L, 13L);
    }

    private Holding holding() {
        Holding holding = new Holding();
        holding.setHoldingId(7L);
        holding.setUserId(1L);
        holding.setStockCode("005930");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("100"));
        holding.setQuantity(BigDecimal.ONE);
        return holding;
    }

    private StockQuote quote() {
        return new StockQuote(
            "KB", "005930", "삼성전자", "KOSPI",
            new BigDecimal("90"), BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, Instant.now()
        );
    }
}
