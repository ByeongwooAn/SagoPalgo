package com.sagopalgo.api.market.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

/**
 * 현재가 서비스가 외부 시세 클라이언트를 선택하는 규칙을 검증합니다.
 */
class MarketPriceServiceTest {

    @Test
    @DisplayName("지원 가능한 외부 클라이언트가 있으면 실제 현재가를 반환한다")
    void currentPriceUsesSupportedClient() {
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketDataProvider("KIS", true, "75300", false)));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("75300");
    }

    @Test
    @DisplayName("지원 가능한 외부 클라이언트가 없으면 등록 매수가를 반환한다")
    void currentPriceFallsBackToBuyPriceWhenNoClientSupportsHolding() {
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketDataProvider("KIS", false, "75300", false)));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("69100");
    }

    @Test
    @DisplayName("외부 Provider가 실패하면 다음 Provider 현재가로 fallback한다")
    void currentPriceFallsBackToNextProviderWhenExternalProviderFails() {
        MarketPriceService service = new MarketPriceService(List.of(
            new FixedMarketDataProvider("KB", true, "75300", true),
            new FixedMarketDataProvider("KIS", true, "75400", false)
        ));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("75400");
    }

    @Test
    @DisplayName("모든 외부 Provider가 실패하면 등록 매수가를 반환한다")
    void currentPriceFallsBackToBuyPriceWhenAllExternalProvidersFail() {
        MarketPriceService service = new MarketPriceService(List.of(
            new FixedMarketDataProvider("KB", true, "75300", true),
            new FixedMarketDataProvider("KIS", true, "75400", true)
        ));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("69100");
    }

    @Test
    @DisplayName("보유 종목 없이 모든 Provider가 실패하면 마지막 외부 데이터 오류를 전파한다")
    void quotePropagatesLastFailureWhenNoFallbackPriceExists() {
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketDataProvider("KB", true, "75300", true)));

        assertThatThrownBy(() -> service.quote(null))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
    }

    @Test
    @DisplayName("관심 종목 시세 Provider가 모두 실패하면 0원 fallback을 반환한다")
    void watchlistQuoteFallsBackToZeroWhenProvidersFail() {
        MarketPriceService service = new MarketPriceService(List.of(
            new FixedMarketDataProvider("KB", true, "75300", true)
        ));

        StockQuote quote = service.quoteMarket(new MarketDataRequest("005930", "KOSPI"));

        assertThat(quote.provider()).isEqualTo("FALLBACK");
        assertThat(quote.currentPrice()).isEqualByComparingTo(BigDecimal.ZERO);
    }

    private Holding holding() {
        Holding holding = new Holding();
        holding.setStockCode("005930");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("69100"));
        return holding;
    }

    private record FixedMarketDataProvider(
        String providerCode,
        boolean supported,
        String currentPrice,
        boolean failing
    ) implements MarketDataProvider {

        @Override
        public String providerCode() {
            return providerCode;
        }

        @Override
        public boolean supports(MarketDataRequest request) {
            return supported;
        }

        @Override
        public StockQuote quote(MarketDataRequest request) {
            if (failing) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "외부 현재가 조회 실패");
            }
            return new StockQuote(
                providerCode,
                request.stockCode(),
                "",
                request.market(),
                new BigDecimal(currentPrice),
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                Instant.now()
            );
        }

        @Override
        public List<StockCandle> candles(MarketDataRequest request, CandleInterval interval, int count) {
            return List.of();
        }
    }
}
