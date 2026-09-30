package com.sagopalgo.api.recommendation.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.alert.service.AlertService;
import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.dashboard.service.DashboardRecommendationEngine;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketCandleService;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.recommendation.client.AiAnalysisGateway;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisRequest;
import com.sagopalgo.api.recommendation.dto.AiInvestmentAnalysisResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import com.sagopalgo.api.research.service.ResearchFeedStore;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import com.sagopalgo.api.watchlist.model.WatchlistItem;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class RecommendationServiceTest {

    @Mock
    private HoldingService holdingService;

    @Mock
    private WatchlistMapper watchlistMapper;

    @Mock
    private MarketPriceService marketPriceService;

    @Mock
    private MarketCandleService marketCandleService;

    @Mock
    private ResearchFeedStore researchFeedStore;

    @Mock
    private AiAnalysisGateway aiAnalysisGateway;

    @Mock
    private RecommendationStore recommendationStore;

    @Mock
    private AlertService alertService;

    private RecommendationService service;

    @BeforeEach
    void setUp() {
        AiAnalysisProperties properties = new AiAnalysisProperties();
        service = new RecommendationService(
            holdingService,
            watchlistMapper,
            marketPriceService,
            marketCandleService,
            researchFeedStore,
            aiAnalysisGateway,
            new DashboardRecommendationEngine(),
            recommendationStore,
            alertService,
            properties,
            new ObjectMapper().findAndRegisterModules()
        );
    }

    @Test
    @DisplayName("가격·뉴스·공시를 AI 서버에 전달하고 추천 결과를 저장한다")
    void analyzeHoldingCombinesSignalsAndStoresResult() {
        HoldingResponse holding = holding("4.2", "9");
        when(holdingService.findOne(1L, 21L)).thenReturn(holding);
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(
            List.of(new NewsArticle(
                "NAVER_NEWS",
                "005930",
                "반도체 수주 증가",
                "https://news.test/1",
                "투자 확대",
                Instant.parse("2026-09-22T01:00:00Z")
            )),
            List.of(new Disclosure(
                "OPEN_DART",
                "005930",
                "00126380",
                "삼성전자",
                "공급계약 체결",
                "202609220001",
                "삼성전자",
                LocalDate.of(2026, 9, 22),
                "https://dart.test/1"
            ))
        ));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(
            new AiInvestmentAnalysisResponse(
                "WEIGHTED_SIGNAL_V1",
                "BUY",
                "BUY_WATCH",
                67,
                "긍정 신호가 우세합니다.",
                List.of(new AiInvestmentAnalysisResponse.Reason(
                    "가격 추세",
                    "종가가 상승했습니다.",
                    "PRICE",
                    12
                ))
            )
        ));
        stubStore();

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.recommendationId()).isEqualTo(99L);
        assertThat(response.status()).isEqualTo("BUY_WATCH");
        assertThat(response.statusLabel()).isEqualTo("매수 관찰");
        verify(alertService).createFromRecommendation(any(StoredRecommendation.class));
        ArgumentCaptor<AiInvestmentAnalysisRequest> requestCaptor = ArgumentCaptor.forClass(
            AiInvestmentAnalysisRequest.class
        );
        verify(aiAnalysisGateway).analyze(requestCaptor.capture());
        assertThat(requestCaptor.getValue().candles()).hasSize(1);
        assertThat(requestCaptor.getValue().news()).hasSize(1);
        assertThat(requestCaptor.getValue().disclosures()).hasSize(1);
        assertThat(requestCaptor.getValue().analysisType()).isEqualTo("HOLDING");
    }

    @Test
    @DisplayName("AI 서버 결과가 없으면 기존 규칙 추천을 같은 저장 계약으로 대체한다")
    void analyzeHoldingFallsBackToRuleEngine() {
        when(holdingService.findOne(1L, 21L)).thenReturn(holding("8.4", "9"));
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(List.of(), List.of()));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.empty());
        stubStore();

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.status()).isEqualTo("TAKE_PROFIT");
        assertThat(response.statusLabel()).isEqualTo("부분 익절 검토");
        assertThat(response.aiSummary()).contains("익절 기준");
    }

    @Test
    void analyzeWatchlistWithoutInventingHoldingProfit() {
        WatchlistItem item = watchlistItem();
        when(watchlistMapper.findByIdAndUserId(12L, 1L)).thenReturn(Optional.of(item));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "75200"));
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(List.of(), List.of()));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "WEIGHTED_SIGNAL_V1", "BUY", "BUY_WATCH", 65, "관심 종목 분석", List.of()
        )));
        stubStore();

        RecommendationResponse response = service.analyzeWatchlist(1L, 12L);

        assertThat(response.analysisContext()).isEqualTo("WATCHLIST");
        assertThat(response.stopLossRate()).isNull();
        ArgumentCaptor<AiInvestmentAnalysisRequest> requestCaptor = ArgumentCaptor.forClass(
            AiInvestmentAnalysisRequest.class
        );
        verify(aiAnalysisGateway).analyze(requestCaptor.capture());
        assertThat(requestCaptor.getValue().analysisType()).isEqualTo("WATCHLIST");
        assertThat(requestCaptor.getValue().buyPrice()).isNull();
        assertThat(requestCaptor.getValue().profitRate()).isNull();
        org.mockito.Mockito.verifyNoInteractions(alertService);
    }

    @Test
    void rejectsFallbackQuoteBeforeSavingWatchlistAnalysis() {
        when(watchlistMapper.findByIdAndUserId(12L, 1L)).thenReturn(Optional.of(watchlistItem()));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("FALLBACK", "0"));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.analyzeWatchlist(1L, 12L))
            .isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);
        org.mockito.Mockito.verifyNoInteractions(aiAnalysisGateway, recommendationStore);
    }

    @Test
    void rejectsAnotherUsersWatchlistItem() {
        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.analyzeWatchlist(2L, 12L))
            .isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);
        org.mockito.Mockito.verifyNoInteractions(marketPriceService, aiAnalysisGateway, recommendationStore);
    }

    @Test
    void watchlistAnalysisFallsBackToNeutralWhenAiIsOffline() {
        when(watchlistMapper.findByIdAndUserId(12L, 1L)).thenReturn(Optional.of(watchlistItem()));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "75200"));
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(List.of(), List.of()));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.empty());
        stubStore();

        RecommendationResponse response = service.analyzeWatchlist(1L, 12L);

        assertThat(response.recommendationType()).isEqualTo("HOLD");
        assertThat(response.aiSummary()).contains("판단을 보류");
    }

    @Test
    void ignoresSellSignalForAnUnownedWatchlistStock() {
        when(watchlistMapper.findByIdAndUserId(12L, 1L)).thenReturn(Optional.of(watchlistItem()));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "75200"));
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(List.of(), List.of()));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "OLD_MODEL", "SELL", "STOP_LOSS_WATCH", 20, "보유 손절", List.of()
        )));
        stubStore();

        RecommendationResponse response = service.analyzeWatchlist(1L, 12L);

        assertThat(response.recommendationType()).isEqualTo("HOLD");
        assertThat(response.status()).isEqualTo("HOLD");
        assertThat(response.aiSummary()).doesNotContain("손절");
    }

    private void stubStore() {
        when(recommendationStore.save(
            any(RecommendationRecord.class),
            anyList(),
            any(AnalysisSnapshotRecord.class)
        )).thenAnswer(invocation -> {
            RecommendationRecord record = invocation.getArgument(0);
            List<RecommendationReasonRecord> reasons = invocation.getArgument(1);
            record.setRecommendationId(99L);
            return new StoredRecommendation(record, reasons);
        });
    }

    private HoldingResponse holding(String profitRate, String takeProfitRate) {
        return new HoldingResponse(
            21L,
            "005930",
            "삼성전자",
            "KOSPI",
            new BigDecimal("70000"),
            new BigDecimal("10"),
            LocalDate.of(2026, 9, 1),
            new BigDecimal("75200"),
            new BigDecimal(profitRate),
            new BigDecimal("-5"),
            new BigDecimal(takeProfitRate),
            "HOLDING",
            "보유"
        );
    }

    private MarketCandleResponse candles() {
        StockCandle candle = new StockCandle(
            "KB",
            "005930",
            "KOSPI",
            LocalDate.of(2026, 9, 22).atStartOfDay(),
            CandleInterval.DAILY,
            new BigDecimal("74800"),
            new BigDecimal("75300"),
            new BigDecimal("74700"),
            new BigDecimal("75200"),
            new BigDecimal("1122334")
        );
        return new MarketCandleResponse(
            "KB",
            "005930",
            "KOSPI",
            CandleInterval.DAILY,
            1,
            List.of(candle)
        );
    }

    private WatchlistItem watchlistItem() {
        WatchlistItem item = new WatchlistItem();
        item.setWatchlistId(12L);
        item.setUserId(1L);
        item.setStockCode("005930");
        item.setStockName("삼성전자");
        item.setMarket("KOSPI");
        return item;
    }

    private StockQuote quote(String provider, String price) {
        return new StockQuote(
            provider, "005930", "삼성전자", "KOSPI", new BigDecimal(price),
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, Instant.now()
        );
    }
}
