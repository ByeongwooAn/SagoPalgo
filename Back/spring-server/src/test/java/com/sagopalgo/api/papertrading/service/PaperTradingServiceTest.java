package com.sagopalgo.api.papertrading.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.dto.PaperBuyRequest;
import com.sagopalgo.api.papertrading.dto.PaperSellRequest;
import com.sagopalgo.api.papertrading.dto.PaperTradingSnapshotResponse;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
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

    private final List<PaperTradeRecord> records = new ArrayList<>();
    private PaperTradingService service;

    @BeforeEach
    void setUp() {
        service = new PaperTradingService(
            tradeMapper,
            capitalService,
            recommendationService,
            marketPriceService
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
    @DisplayName("BUY AI 추천을 현재가로 가상 체결하고 현금과 포지션을 계산한다")
    void buysFromAiRecommendation() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(new MarketDataRequest("005930", "KOSPI")))
            .thenReturn(quote("100"));

        PaperTradingSnapshotResponse response = service.buyFromRecommendation(
            1L,
            11L,
            new PaperBuyRequest(new BigDecimal("10"))
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
        when(marketPriceService.quoteMarket(new MarketDataRequest("005930", "KOSPI")))
            .thenReturn(quote("90"));

        PaperTradingSnapshotResponse response = service.sell(
            1L,
            new PaperSellRequest("005930", "KOSPI", new BigDecimal("4"))
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
            new PaperBuyRequest(BigDecimal.ONE)
        ))
            .isInstanceOf(ApiException.class)
            .hasMessage("매수 AI 신호만 모의매수할 수 있습니다.");

        assertThat(records).isEmpty();
    }

    @Test
    @DisplayName("실제 현재가를 얻지 못하면 모의 체결을 차단한다")
    void rejectsFallbackExecutionQuote() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(new MarketDataRequest("005930", "KOSPI")))
            .thenReturn(new StockQuote(
                "FALLBACK", "005930", "삼성전자", "KOSPI",
                new BigDecimal("100"), BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, Instant.now()
            ));

        assertThatThrownBy(() -> service.buyFromRecommendation(
            1L,
            11L,
            new PaperBuyRequest(BigDecimal.ONE)
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
            new PaperSellRequest("005930", "KOSPI", new BigDecimal("11"))
        ))
            .isInstanceOf(ApiException.class)
            .hasMessage("보유한 모의 수량보다 많이 매도할 수 없습니다.");

        assertThat(records).hasSize(1);
    }

    @Test
    void recordedTradesSurviveServiceRestartAndCapitalChangeDoesNotRewriteThem() {
        when(recommendationService.findOne(1L, 11L)).thenReturn(recommendation("BUY"));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("100"));
        service.buyFromRecommendation(1L, 11L, new PaperBuyRequest(new BigDecimal("3")));
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("110"));
        service.sell(1L, new PaperSellRequest("005930", "KOSPI", BigDecimal.ONE));

        var restarted = new PaperTradingService(tradeMapper, capitalService, recommendationService, marketPriceService);
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
            "005930",
            "삼성전자",
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

    private PaperTradeRecord buyRecord() {
        PaperTradeRecord record = new PaperTradeRecord();
        record.setTradeRecordId(1L);
        record.setUserId(1L);
        record.setRecommendationId(11L);
        record.setStockCode("005930");
        record.setStockName("삼성전자");
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
            "KB", "005930", "삼성전자", "KOSPI",
            new BigDecimal(currentPrice), BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, Instant.now()
        );
    }
}
