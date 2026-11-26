package com.sagopalgo.api.papertrading.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.dto.PaperBuyRequest;
import com.sagopalgo.api.papertrading.dto.PaperSellRequest;
import com.sagopalgo.api.papertrading.dto.PaperTradingSnapshotResponse;
import com.sagopalgo.api.papertrading.dto.UsPaperTradeRequest;
import com.sagopalgo.api.papertrading.dto.UsPaperTradeRequest.Side;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.service.DailySignalService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PaperTradingServiceTest {

    @Mock
    private PaperTradeMapper tradeMapper;

    @Mock
    private CapitalService capitalService;

    @Mock
    private RecommendationService recommendationService;

    @Mock
    private MarketPriceService marketPriceService;

    @Mock
    private KisMarketPriceClient kis;

    @Mock
    private DailySignalService dailySignals;

    private final List<PaperTradeRecord> records = new ArrayList<>();
    private final List<PaperTradeRecord> usRecords = new ArrayList<>();
    private PaperTradingService service;

    @BeforeEach
    void setUp() {
        service = new PaperTradingService(
            tradeMapper,
            capitalService,
            recommendationService,
            marketPriceService,
            kis,
            dailySignals
        );
        lenient().when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            new BigDecimal("1000000"),
            new BigDecimal("100000"),
            new BigDecimal("200000"),
            new BigDecimal("0.02")
        ));
        lenient().when(tradeMapper.findAllByUserId(1L)).thenAnswer(ignored -> List.copyOf(records));
        lenient().when(tradeMapper.insert(any())).thenAnswer(invocation -> {
            PaperTradeRecord record = invocation.getArgument(0);
            record.setTradeRecordId((long) records.size() + 1);
            records.add(record);
            return 1;
        });
    }

    @Test
    void usdLedgerReconcilesRoundedFractionalFillsWithoutChangingKrwLedger() {
        stubUsLedger("1000");
        when(marketPriceService.getUsQuote("MSFT", "NASDAQ"))
            .thenReturn(usQuote("222.2222"), usQuote("250.1234"), usQuote("260.0100"));

        var buy = service.tradeUs(1L, usOrder(Side.BUY, "1.5000", 1));
        assertThat(buy.currency()).isEqualTo("USD");
        assertThat(buy.summary().cashBalance()).isEqualByComparingTo("666.67");
        assertThat(buy.trades().get(0).tradePrice()).isEqualByComparingTo("222.2222");
        assertThat(buy.trades().get(0).tradeAmount()).isEqualByComparingTo("333.33");

        var partial = service.tradeUs(1L, usOrder(Side.SELL, "0.7000", 2));
        assertThat(partial.summary().cashBalance()).isEqualByComparingTo("841.76");
        assertThat(partial.summary().realizedProfit()).isEqualByComparingTo("19.54");
        assertThat(partial.summary().unrealizedProfit()).isEqualByComparingTo("22.32");
        assertThat(partial.summary().totalProfit()).isEqualByComparingTo("41.86");
        assertThat(partial.positions().get(0).quantity()).isEqualByComparingTo("0.8");

        var closed = service.tradeUs(1L, usOrder(Side.SELL, "0.8", 3));
        assertThat(closed.positions()).isEmpty();
        assertThat(closed.summary().cashBalance()).isEqualByComparingTo("1049.77");
        assertThat(closed.summary().realizedProfit()).isEqualByComparingTo("49.77");
        assertThat(service.getSnapshot(1L).summary().cashBalance()).isEqualByComparingTo("1000000");
        assertThat(records).isEmpty();
    }

    @Test
    void retryUsesSameUsFillAndUnpricedPositionsRemainAtCost() {
        stubUsLedger("500");
        when(marketPriceService.getUsQuote("MSFT", "NASDAQ"))
            .thenReturn(usQuote("123.45"))
            .thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR));
        var order = usOrder(Side.BUY, "2", 1);
        service.tradeUs(1L, order);
        var replay = service.tradeUs(1L, order);

        assertThat(usRecords).hasSize(1);
        assertThat(replay.summary().cashBalance()).isEqualByComparingTo("253.10");
        assertThat(replay.summary().openPositionValue()).isEqualByComparingTo("246.90");
        assertThat(replay.positions().get(0).provider()).isEqualTo("FALLBACK");
        assertThatThrownBy(() -> service.tradeUs(1L, usOrder(Side.BUY, "3", 1)))
            .isInstanceOf(ApiException.class).extracting("errorCode").isEqualTo(ErrorCode.DUPLICATE_RESOURCE);
        assertThatThrownBy(() -> service.tradeUs(1L, usOrder(Side.SELL, "1", 2)))
            .isInstanceOf(ApiException.class).extracting("errorCode").isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        assertThat(usRecords).hasSize(1);
    }

    @Test
    void usTradeChecksUsdCashAndHoldingsBeforeWriting() {
        when(tradeMapper.findUsCapital(1L)).thenReturn(new BigDecimal("100"));
        when(marketPriceService.getUsQuote("MSFT", "NASDAQ")).thenReturn(usQuote("123.45"));
        assertThatThrownBy(() -> service.tradeUs(1L, usOrder(Side.BUY, "1", 1)))
            .isInstanceOf(ApiException.class).hasMessage("USD 모의 현금 잔액이 부족합니다.");
        assertThatThrownBy(() -> service.tradeUs(1L, usOrder(Side.SELL, "1", 2)))
            .isInstanceOf(ApiException.class).hasMessageContaining("모의 수량보다 많이");
        verify(tradeMapper, never()).insertUsTrade(any());
    }

    @Test
    void openingUsdAccountDoesNotRequireDomesticCapitalAndIsIdempotent() {
        when(tradeMapper.findUsCapital(2L)).thenReturn(null, new BigDecimal("5000.00"));
        assertThat(service.openUsAccount(2L, new BigDecimal("5000")).summary().cashBalance())
            .isEqualByComparingTo("5000");
        assertThat(service.openUsAccount(2L, new BigDecimal("5000")).summary().cashBalance())
            .isEqualByComparingTo("5000");
        verify(tradeMapper).insertUsAccount(2L, new BigDecimal("5000"));
        verify(capitalService, never()).findByUserId(2L);
    }

    private void stubUsLedger(String capital) {
        when(tradeMapper.findUsCapital(1L)).thenReturn(new BigDecimal(capital));
        when(tradeMapper.findUsTrades(1L)).thenAnswer(ignored -> List.copyOf(usRecords));
        when(tradeMapper.insertUsTrade(any())).thenAnswer(invocation -> {
            PaperTradeRecord record = invocation.getArgument(0);
            record.setTradeRecordId((long) usRecords.size() + 1);
            usRecords.add(record);
            return 1;
        });
    }

    private UsPaperTradeRequest usOrder(Side side, String quantity, int id) {
        return new UsPaperTradeRequest(" msft ", "nasdaq", side, new BigDecimal(quantity), "%032x".formatted(id));
    }

    private StockQuote usQuote(String price) {
        return new StockQuote("KIS", "MSFT", "", "NASDAQ", new BigDecimal(price),
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, Instant.now());
    }

    @Test
    @DisplayName("BUY AI 추천을 현재가로 가상 체결하고 현금과 포지션을 계산한다")
    void buysFromAiRecommendation() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(new MarketDataRequest("035420", "KOSPI")))
            .thenReturn(quote("100"));

        PaperTradingSnapshotResponse response = service.buyFromRecommendation(
            1L,
            11L,
            new PaperBuyRequest(new BigDecimal("10"), requestId(1))
        );

        assertThat(records).singleElement().satisfies(record -> {
            assertThat(record.getExecutionMode()).isEqualTo("PAPER");
            assertThat(record.getRecommendationId()).isEqualTo(11L);
            assertThat(record.getTradeType()).isEqualTo("BUY");
        });
        assertThat(response.summary().cashBalance()).isEqualByComparingTo("999000");
        assertThat(response.summary().totalAsset()).isEqualByComparingTo("1000000");
        assertThat(response.positions()).singleElement().satisfies(position -> {
            assertThat(position.quantity()).isEqualByComparingTo("10");
            assertThat(position.averagePrice()).isEqualByComparingTo("100");
            assertThat(position.provider()).isEqualTo("KB");
        });
    }

    @Test
    @DisplayName("가상 포지션 일부를 매도하면 실현손익과 승률 및 최대 손실을 계산한다")
    void sellsPaperPositionAndCalculatesMetrics() {
        records.add(buyRecord());
        when(marketPriceService.quoteMarket(new MarketDataRequest("035420", "KOSPI")))
            .thenReturn(quote("90"));

        PaperTradingSnapshotResponse response = service.sell(
            1L,
            new PaperSellRequest("035420", "KOSPI", new BigDecimal("4"), requestId(2))
        );

        assertThat(response.summary().realizedProfit()).isEqualByComparingTo("-40");
        assertThat(response.summary().unrealizedProfit()).isEqualByComparingTo("-60");
        assertThat(response.summary().totalProfit()).isEqualByComparingTo("-100");
        assertThat(response.summary().completedTrades()).isEqualTo(1);
        assertThat(response.summary().winRate()).isEqualByComparingTo("0");
        assertThat(response.summary().maxLoss()).isEqualByComparingTo("40");
        assertThat(response.positions()).singleElement().satisfies(position ->
            assertThat(position.quantity()).isEqualByComparingTo("6")
        );
    }

    @Test
    @DisplayName("BUY가 아닌 AI 추천은 모의매수에 사용할 수 없다")
    void rejectsNonBuyRecommendation() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("HOLD"));

        assertThatThrownBy(() -> service.buyFromRecommendation(
            1L,
            11L,
            new PaperBuyRequest(BigDecimal.ONE, requestId(1))
        ))
            .isInstanceOf(ApiException.class)
            .hasMessage("매수 AI 신호만 모의매수할 수 있습니다.");

        assertThat(records).isEmpty();
    }

    @Test
    @DisplayName("실제 현재가를 얻지 못하면 모의 체결을 차단한다")
    void rejectsFallbackExecutionQuote() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(new MarketDataRequest("035420", "KOSPI")))
            .thenReturn(new StockQuote(
                "FALLBACK", "035420", "NAVER", "KOSPI",
                new BigDecimal("100"), BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, Instant.now()
            ));

        assertThatThrownBy(() -> service.buyFromRecommendation(
            1L,
            11L,
            new PaperBuyRequest(BigDecimal.ONE, requestId(1))
        ))
            .isInstanceOf(ApiException.class)
            .hasMessage("실제 현재가를 확인할 수 없어 모의 체결하지 않았습니다.");

        assertThat(records).isEmpty();
    }

    @Test
    @DisplayName("보유 수량보다 많은 모의매도는 차단한다")
    void rejectsSellQuantityAbovePosition() {
        records.add(buyRecord());

        assertThatThrownBy(() -> service.sell(
            1L,
            new PaperSellRequest("035420", "KOSPI", new BigDecimal("11"), requestId(2))
        ))
            .isInstanceOf(ApiException.class)
            .hasMessage("보유한 모의 수량보다 많이 매도할 수 없습니다.");

        assertThat(records).hasSize(1);
    }

    @Test
    void recordedTradesSurviveServiceRestartAndCapitalChangeDoesNotRewriteThem() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("100"));
        service.buyFromRecommendation(1L, 11L, new PaperBuyRequest(new BigDecimal("3"), requestId(1)));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("110"));
        service.sell(1L, new PaperSellRequest("035420", "KOSPI", BigDecimal.ONE, requestId(2)));

        var restarted = new PaperTradingService(tradeMapper, capitalService, recommendationService,
            marketPriceService, kis, dailySignals);
        var restored = restarted.getSnapshot(1L);
        assertThat(restored.trades()).hasSize(2);
        assertThat(restored.summary().cashBalance()).isEqualByComparingTo("999810");
        assertThat(restored.summary().totalProfit()).isEqualByComparingTo("30");
        assertThat(records).allSatisfy(record -> assertThat(record.getExecutionMode()).isEqualTo("PAPER"));

        when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            new BigDecimal("2000000"), new BigDecimal("200000"), new BigDecimal("400000"), new BigDecimal("0.02")));
        var revalued = restarted.getSnapshot(1L);
        assertThat(revalued.summary().cashBalance()).isEqualByComparingTo("1999810");
        assertThat(revalued.trades()).hasSize(2);
        assertThat(records.get(0).getTradePrice()).isEqualByComparingTo("100");
    }

    @Test
    void unsetCapitalReturnsAnActionableCodeWithoutDeletingPaperRecords() {
        records.add(buyRecord());
        when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, new BigDecimal("0.02")));
        assertThatThrownBy(() -> service.getSnapshot(1L)).isInstanceOf(ApiException.class)
            .extracting("errorCode").isEqualTo(com.sagopalgo.api.common.exception.ErrorCode.PAPER_CAPITAL_REQUIRED);
        assertThat(records).hasSize(1);
    }

    private RecommendationResponse recommendation(String recommendationType) {
        return new RecommendationResponse(
            11L,
            "035420",
            "NAVER",
            "KOSPI",
            recommendationType,
            "BUY_STRONG",
            "강한 매수",
            87,
            new BigDecimal("100"),
            new BigDecimal("-5"),
            new BigDecimal("10"),
            "테스트 추천",
            LocalDateTime.now(),
            List.of(),
            "HOLDING"
        );
    }

    private String requestId(int id) {
        return "%032x".formatted(id);
    }

    private PaperTradeRecord buyRecord() {
        PaperTradeRecord record = new PaperTradeRecord();
        record.setTradeRecordId(1L);
        record.setUserId(1L);
        record.setRecommendationId(11L);
        record.setStockCode("035420");
        record.setStockName("NAVER");
        record.setMarket("KOSPI");
        record.setTradeType("BUY");
        record.setExecutionMode("PAPER");
        record.setTradePrice(new BigDecimal("100"));
        record.setQuantity(new BigDecimal("10"));
        record.setRealizedProfit(BigDecimal.ZERO);
        record.setTradeDate(LocalDateTime.now().minusDays(1));
        return record;
    }

    private StockQuote quote(String currentPrice) {
        return new StockQuote(
            "KB", "035420", "NAVER", "KOSPI",
            new BigDecimal(currentPrice), BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, Instant.now()
        );
    }
}
