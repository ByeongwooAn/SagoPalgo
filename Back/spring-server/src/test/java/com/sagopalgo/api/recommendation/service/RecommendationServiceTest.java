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
import com.sagopalgo.api.holding.dto.PortfolioCostExposure;
import com.sagopalgo.api.holding.model.Holding;
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
import com.sagopalgo.api.recommendation.dto.DailySignal;
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
import java.time.OffsetDateTime;
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

    @Mock
    private DailySignalService dailySignalService;

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
            new ObjectMapper().findAndRegisterModules(),
            dailySignalService
        );
    }

    @Test
    @DisplayName("가격·뉴스·공시를 AI 서버에 전달하고 추천 결과를 저장한다")
    void analyzeHoldingCombinesSignalsAndStoresResult() throws Exception {
        when(holdingService.findRecord(1L, 21L)).thenReturn(holding("9"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "75200"));
        when(holdingService.costExposure(1L, "005930", "KOSPI")).thenReturn(Optional.of(
            new PortfolioCostExposure(new BigDecimal("40"), new BigDecimal("18"), new BigDecimal("20"))
        ));
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
        when(dailySignalService.analyze("005930", "KOSPI")).thenReturn(DailySignal.withheld(
            "BAR_NOT_FINAL", LocalDate.of(2026, 11, 18), OffsetDateTime.parse("2026-11-18T16:00:00+09:00")));
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
        assertThat(requestCaptor.getValue().currentPrice()).isEqualByComparingTo("75200");
        assertThat(requestCaptor.getValue().profitRate()).isEqualByComparingTo("7.43");
        assertThat(requestCaptor.getValue().portfolioWeightRate()).isEqualByComparingTo("40");
        assertThat(requestCaptor.getValue().capitalWeightRate()).isEqualByComparingTo("18");
        assertThat(requestCaptor.getValue().maxCapitalWeightRate()).isEqualByComparingTo("20");
        var snapshotCaptor = ArgumentCaptor.forClass(AnalysisSnapshotRecord.class);
        verify(recommendationStore).save(any(), anyList(), snapshotCaptor.capture());
        var dailySignal = new ObjectMapper().readTree(snapshotCaptor.getValue().getRawPayload()).path("dailySignal");
        assertThat(dailySignal.path("holdReason").asText()).isEqualTo("BAR_NOT_FINAL");
        assertThat(dailySignal.path("basisDate").asText()).isEqualTo("2026-11-18");
    }

    @Test
    @DisplayName("AI 서버 결과가 없으면 기존 규칙 추천을 같은 저장 계약으로 대체한다")
    void analyzeHoldingFallsBackToRuleEngine() {
        when(holdingService.findRecord(1L, 21L)).thenReturn(holding("9"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "77000"));
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
    void rejectsFallbackBuyPriceBeforeHoldingAnalysis() {
        when(holdingService.findRecord(1L, 21L)).thenReturn(holding("9"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("FALLBACK", "70000"));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.analyzeHolding(1L, 21L))
            .isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class)
            .hasMessageContaining("실제 현재가");
        org.mockito.Mockito.verifyNoInteractions(aiAnalysisGateway, recommendationStore, alertService);
    }

    @Test
    void rejectsMissingHoldingPriceBeforeAnalysis() {
        when(holdingService.findRecord(1L, 21L)).thenReturn(holding("9"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "0"));

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> service.analyzeHolding(1L, 21L))
            .isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);
        org.mockito.Mockito.verifyNoInteractions(aiAnalysisGateway, recommendationStore, alertService);
    }

    @Test
    void replacesBuySignalAtStopLossWithRuleFallback() {
        stubHoldingAnalysis("66000");
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "OLD_MODEL", "BUY", "BUY_STRONG", 90, "잘못된 매수 신호", List.of()
        )));

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.status()).isEqualTo("STOP_LOSS_WATCH");
        assertThat(response.recommendationType()).isEqualTo("SELL");
        assertThat(response.aiSummary()).doesNotContain("잘못된 매수 신호");
    }

    @Test
    void replacesMismatchedHoldingStatusAndTypeWithRuleFallback() {
        stubHoldingAnalysis("75200");
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "OLD_MODEL", "SELL", "BUY_WATCH", 65, "상태와 유형 불일치", List.of()
        )));

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.status()).isEqualTo("HOLD");
        assertThat(response.recommendationType()).isEqualTo("HOLD");
    }

    @Test
    void rejectsBuySignalAboveCapitalWeightLimit() {
        stubHoldingAnalysis("75200");
        when(holdingService.costExposure(1L, "005930", "KOSPI")).thenReturn(Optional.of(
            new PortfolioCostExposure(new BigDecimal("40"), new BigDecimal("22"), new BigDecimal("20"))
        ));
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "OLD_MODEL", "BUY", "BUY_WATCH", 65, "비중 초과 매수 신호", List.of()
        )));

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.status()).isEqualTo("HOLD");
        assertThat(response.recommendationType()).isEqualTo("HOLD");
        assertThat(response.aiSummary()).doesNotContain("비중 초과 매수 신호");
    }

    @Test
    void rejectsTakeProfitSignalBelowThreshold() {
        stubHoldingAnalysis("75200");
        when(aiAnalysisGateway.analyze(any())).thenReturn(Optional.of(new AiInvestmentAnalysisResponse(
            "OLD_MODEL", "SELL", "TAKE_PROFIT", 80, "잘못된 익절 신호", List.of()
        )));

        RecommendationResponse response = service.analyzeHolding(1L, 21L);

        assertThat(response.status()).isEqualTo("HOLD");
        assertThat(response.aiSummary()).doesNotContain("잘못된 익절 신호");
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
        assertThat(requestCaptor.getValue().portfolioWeightRate()).isNull();
        verify(alertService).createFromRecommendation(any());
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

    @Test
    void storedEvidenceExposesTheModelAndInputCountsWithoutReturningRawPayload() {
        RecommendationRecord record = new RecommendationRecord();
        record.setRecommendationId(99L); record.setUserId(1L); record.setStatus("HOLD");
        record.setAnalysisContext("WATCHLIST");
        record.setAnalysisEvidence("""
            {"modelVersion":"WATCHLIST_SAFE_FALLBACK_V1","candleCount":0,"newsCount":2,"disclosureCount":1,
             "dailySignal":{"decision":"WAIT","basisDate":"2026-10-30","expiresAt":"2026-11-02T15:30:00+09:00",
                            "probability":0.43210123456789,"threshold":0.5}}
            """);
        when(recommendationStore.findById(1L, 99L)).thenReturn(Optional.of(new StoredRecommendation(record, List.of())));
        var response = service.findOne(1L, 99L);
        assertThat(response.evidence().modelVersion()).isEqualTo("WATCHLIST_SAFE_FALLBACK_V1");
        assertThat(response.evidence().newsCount()).isEqualTo(2);
        assertThat(response.evidence().candleCount()).isZero();
        assertThat(response.evidence().dailySignal().probability()).isEqualTo(0.43210123456789);
        assertThat(response.evidence().dailySignal().expiresAt())
            .isEqualTo(OffsetDateTime.parse("2026-11-02T15:30:00+09:00"));
    }

    @Test
    void malformedLegacyEvidenceRemainsUnknown() {
        RecommendationRecord record = new RecommendationRecord();
        record.setRecommendationId(99L); record.setUserId(1L); record.setStatus("HOLD");
        record.setAnalysisContext("HOLDING"); record.setAnalysisEvidence("not-json");
        when(recommendationStore.findById(1L, 99L)).thenReturn(Optional.of(new StoredRecommendation(record, List.of())));
        assertThat(service.findOne(1L, 99L).evidence()).isNull();
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

    private void stubHoldingAnalysis(String price) {
        when(holdingService.findRecord(1L, 21L)).thenReturn(holding("9"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", price));
        when(researchFeedStore.find(any())).thenReturn(new StoredResearchFeed(List.of(), List.of()));
        when(marketCandleService.getCandles(any(), any(), any(), any(Integer.class)))
            .thenReturn(candles());
        stubStore();
    }

    private Holding holding(String takeProfitRate) {
        Holding holding = new Holding();
        holding.setHoldingId(21L);
        holding.setUserId(1L);
        holding.setStockCode("005930");
        holding.setStockName("삼성전자");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("70000"));
        holding.setQuantity(new BigDecimal("10"));
        holding.setBuyDate(LocalDate.of(2026, 9, 1));
        holding.setStopLossRate(new BigDecimal("-5"));
        holding.setTakeProfitRate(new BigDecimal(takeProfitRate));
        holding.setStatus("HOLDING");
        return holding;
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
