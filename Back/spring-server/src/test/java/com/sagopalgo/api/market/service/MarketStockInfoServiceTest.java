package com.sagopalgo.api.market.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.DomesticStockIdentity;

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

    @Test
    void codeOnlyLookupValidatesIdentityAndFallsBackFromWrongSymbol() {
        var service = new MarketStockInfoService(List.of(
            identityProvider("KIS", new DomesticStockIdentity("KIS", "000660", "다른 종목", "KOSPI")),
            identityProvider("TOSS", new DomesticStockIdentity("TOSS", "005930", " 삼성전자 ", "KOSPI"))));
        var result = service.lookupDomesticStock(" 005930 ");
        assertThat(result.stockCode()).isEqualTo("005930");
        assertThat(result.stockName()).isEqualTo("삼성전자");
        assertThat(result.provider()).isEqualTo("TOSS");
    }

    @Test
    void invalidCodeIsRejectedBeforeProviderCall() {
        var service = new MarketStockInfoService(List.of(identityProvider("KIS", null)));
        assertThatThrownBy(() -> service.lookupDomesticStock("660"))
            .isInstanceOf(ApiException.class).extracting("errorCode").isEqualTo(ErrorCode.VALIDATION_ERROR);
    }

    @Test
    void missingMarketIsNotAcceptedAsAValidIdentity() {
        var service = new MarketStockInfoService(List.of(identityProvider("KIS",
            new DomesticStockIdentity("KIS", "005930", "삼성전자", null))));
        assertThatThrownBy(() -> service.lookupDomesticStock("005930"))
            .isInstanceOf(ApiException.class).extracting("errorCode").isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
    }

    @Test
    void missingProvidersExplainManualEntryInsteadOfFabricatingName() {
        assertThatThrownBy(() -> new MarketStockInfoService(List.of()).lookupDomesticStock("000660"))
            .hasMessageContaining("직접 입력");
    }

    private MarketDataProvider identityProvider(String code, DomesticStockIdentity identity) {
        return new MarketDataProvider() {
            public String providerCode() { return code; }
            public boolean supports(MarketDataRequest request) { throw new AssertionError("시장 입력에 의존하면 안 됩니다."); }
            public StockQuote quote(MarketDataRequest request) { throw new AssertionError("가격을 만들면 안 됩니다."); }
            public Optional<DomesticStockIdentity> domesticStockIdentity(String stockCode) { return Optional.ofNullable(identity); }
        };
    }
}
