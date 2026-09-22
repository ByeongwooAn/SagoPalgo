package com.sagopalgo.api.market.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.market.dto.MarketStockInfoResponse;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockInfo;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class MarketStockInfoServiceTest {

    @Test
    @DisplayName("종목 정보를 제공하는 첫 Provider의 결과를 반환한다")
    void returnsFirstAvailableStockInfo() {
        MarketStockInfoService service = new MarketStockInfoService(List.of(
            provider("KB", Optional.empty()),
            provider("TOSS", Optional.of(stockInfo()))
        ));

        MarketStockInfoResponse response = service.getStockInfo("005930", "kospi");

        assertThat(response.provider()).isEqualTo("TOSS");
        assertThat(response.stockName()).isEqualTo("삼성전자");
        assertThat(response.market()).isEqualTo("KOSPI");
    }

    private MarketDataProvider provider(String code, Optional<StockInfo> info) {
        return new MarketDataProvider() {
            @Override
            public String providerCode() {
                return code;
            }

            @Override
            public boolean supports(MarketDataRequest request) {
                return true;
            }

            @Override
            public StockQuote quote(MarketDataRequest request) {
                throw new UnsupportedOperationException();
            }

            @Override
            public Optional<StockInfo> stockInfo(MarketDataRequest request) {
                return info;
            }
        };
    }

    private StockInfo stockInfo() {
        return new StockInfo(
            "TOSS", "005930", "삼성전자", "SamsungElec", "KOSPI", "STOCK",
            true, "ACTIVE", "KRW", LocalDate.of(1975, 6, 11), null,
            new BigDecimal("5919637922"), true, false
        );
    }
}
