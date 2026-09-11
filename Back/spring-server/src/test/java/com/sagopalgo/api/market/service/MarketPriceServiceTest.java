package com.sagopalgo.api.market.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.client.MarketPriceClient;
import java.math.BigDecimal;
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
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketPriceClient(true, "75300", false)));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("75300");
    }

    @Test
    @DisplayName("지원 가능한 외부 클라이언트가 없으면 등록 매수가를 반환한다")
    void currentPriceFallsBackToBuyPriceWhenNoClientSupportsHolding() {
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketPriceClient(false, "75300", false)));

        BigDecimal currentPrice = service.currentPrice(holding());

        assertThat(currentPrice).isEqualByComparingTo("69100");
    }

    @Test
    @DisplayName("외부 클라이언트 실패는 숨기지 않고 API 예외로 전파한다")
    void currentPricePropagatesExternalClientFailure() {
        MarketPriceService service = new MarketPriceService(List.of(new FixedMarketPriceClient(true, "75300", true)));

        assertThatThrownBy(() -> service.currentPrice(holding()))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
    }

    private Holding holding() {
        Holding holding = new Holding();
        holding.setStockCode("005930");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("69100"));
        return holding;
    }

    private record FixedMarketPriceClient(
        boolean supported,
        String currentPrice,
        boolean failing
    ) implements MarketPriceClient {

        @Override
        public boolean supports(Holding holding) {
            return supported;
        }

        @Override
        public BigDecimal currentPrice(Holding holding) {
            if (failing) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "외부 현재가 조회 실패");
            }
            return new BigDecimal(currentPrice);
        }
    }
}
