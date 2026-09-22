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
        AlertEvaluationScheduler scheduler = new AlertEvaluationScheduler(
            holdingService,
            recommendationService,
            marketPriceService,
            eventAlertService,
            portfolioRiskAlertService,
            new PersonalModeProperties(true, 1L, "개인 사용자", "local@sagopalgo.local")
        );
        Holding holding = holding();
        StockQuote quote = quote();
        when(holdingService.findActiveIds(1L)).thenReturn(List.of(7L));
        when(holdingService.findRecord(1L, 7L)).thenReturn(holding);
        when(marketPriceService.quote(holding)).thenReturn(quote);

        scheduler.analyzeHoldings();

        verify(eventAlertService).createPriceAlerts(holding, quote);
        verify(recommendationService).analyzeHolding(1L, 7L);
        @SuppressWarnings("unchecked")
        ArgumentCaptor<List<PortfolioPosition>> captor = ArgumentCaptor.forClass(List.class);
        verify(portfolioRiskAlertService).createAlerts(org.mockito.ArgumentMatchers.eq(1L), captor.capture());
        assertThat(captor.getValue()).containsExactly(new PortfolioPosition(holding, quote));
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
