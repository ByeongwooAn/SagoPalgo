package com.sagopalgo.api.market.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class MarketCandleServiceTest {

    @Test
    @DisplayName("앞 Provider가 실패하면 다음 Provider의 캔들을 반환한다")
    void candlesFallBackToNextProvider() {
        MarketCandleService service = new MarketCandleService(List.of(
            new FixedCandleProvider("KB", true, true, List.of()),
            new FixedCandleProvider("KIS", true, false, List.of(candle("KIS")))
        ));

        MarketCandleResponse response = service.getCandles("005930", "kospi", CandleInterval.DAILY, 20);

        assertThat(response.provider()).isEqualTo("KIS");
        assertThat(response.market()).isEqualTo("KOSPI");
        assertThat(response.count()).isEqualTo(1);
        assertThat(response.candles()).extracting(StockCandle::provider).containsExactly("KIS");
    }

    @Test
    @DisplayName("빈 캔들을 반환한 Provider는 건너뛰고 다음 Provider를 사용한다")
    void candlesSkipEmptyProviderResult() {
        MarketCandleService service = new MarketCandleService(List.of(
            new FixedCandleProvider("KB", true, false, List.of()),
            new FixedCandleProvider("KIS", true, false, List.of(candle("KIS")))
        ));

        MarketCandleResponse response = service.getCandles("005930", "KOSPI", CandleInterval.WEEKLY, 20);

        assertThat(response.provider()).isEqualTo("KIS");
    }

    @Test
    @DisplayName("사용 가능한 캔들 Provider가 없으면 임의 가격 없이 외부 데이터 오류를 반환한다")
    void candlesFailWhenNoProviderIsAvailable() {
        MarketCandleService service = new MarketCandleService(List.of(
            new FixedCandleProvider("KB", false, false, List.of())
        ));

        assertThatThrownBy(() -> service.getCandles("005930", "KOSPI", CandleInterval.DAILY, 20))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
    }

    @Test
    @DisplayName("분봉 또는 100건 초과 요청은 검증 오류로 거절한다")
    void candlesValidateIntervalAndCount() {
        MarketCandleService service = new MarketCandleService(List.of());

        assertThatThrownBy(() -> service.getCandles("005930", "KOSPI", CandleInterval.MINUTE, 20))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.VALIDATION_ERROR);
        assertThatThrownBy(() -> service.getCandles("005930", "KOSPI", CandleInterval.DAILY, 101))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.VALIDATION_ERROR);
    }

    private StockCandle candle(String provider) {
        return new StockCandle(
            provider,
            "005930",
            "KOSPI",
            LocalDate.of(2026, 9, 22).atStartOfDay(),
            CandleInterval.DAILY,
            new BigDecimal("75200"),
            new BigDecimal("75500"),
            new BigDecimal("74900"),
            new BigDecimal("75300"),
            new BigDecimal("1234567")
        );
    }

    private record FixedCandleProvider(
        String providerCode,
        boolean supported,
        boolean failing,
        List<StockCandle> result
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
            throw new UnsupportedOperationException();
        }

        @Override
        public List<StockCandle> candles(MarketDataRequest request, CandleInterval interval, int count) {
            if (failing) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "외부 캔들 조회 실패");
            }
            return result;
        }
    }
}
