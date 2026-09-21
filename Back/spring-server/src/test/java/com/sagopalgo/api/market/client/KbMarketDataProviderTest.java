package com.sagopalgo.api.market.client;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/**
 * KB증권 현재가 응답을 내부 표준 시세 모델로 변환하는 규칙을 검증합니다.
 */
class KbMarketDataProviderTest {

    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    @Test
    @DisplayName("IVU10140 현재가 응답을 표준 Quote 모델로 변환한다")
    void quoteMapsKbCurrentPriceResponse() throws Exception {
        KbMarketDataProvider provider = new KbMarketDataProvider(new FixtureKbClient(json("""
            {
              "dataBody": {
                "is_nm": "삼성전자",
                "now_prc": "75,300",
                "bdy_cmpr": "100",
                "up_dwn_r_p2": "0.13",
                "acml_vlm": "1234567",
                "opn_prc": "75,200",
                "hgh_prc": "75,500",
                "lw_prc": "74,900",
                "bdy_cls_prc": "75,200"
              }
            }
            """), true));

        StockQuote quote = provider.quote(new MarketDataRequest("005930", "KOSPI"));

        assertThat(quote.provider()).isEqualTo("KB");
        assertThat(quote.stockCode()).isEqualTo("005930");
        assertThat(quote.stockName()).isEqualTo("삼성전자");
        assertThat(quote.currentPrice()).isEqualByComparingTo("75300");
        assertThat(quote.changePrice()).isEqualByComparingTo("100");
        assertThat(quote.changeRate()).isEqualByComparingTo("0.13");
        assertThat(quote.volume()).isEqualByComparingTo("1234567");
        assertThat(quote.openPrice()).isEqualByComparingTo("75200");
        assertThat(quote.highPrice()).isEqualByComparingTo("75500");
        assertThat(quote.lowPrice()).isEqualByComparingTo("74900");
        assertThat(quote.previousClose()).isEqualByComparingTo("75200");
    }

    @Test
    @DisplayName("IVS11560 통합차트 응답을 시간 오름차순 표준 캔들로 변환한다")
    void candlesMapKbChartResponse() throws Exception {
        KbMarketDataProvider provider = new KbMarketDataProvider(new FixtureKbClient(json("{}"), json("""
            {
              "dataBody": {
                "out2": [
                  {
                    "dt": "20260922",
                    "opn_prc_p2": "75,200",
                    "hgh_prc_p2": "75,500",
                    "lw_prc_p2": "74,900",
                    "cls_prc_p2": "75,300",
                    "vlm": "1,234,567"
                  },
                  {
                    "dt": "20260921",
                    "opn_prc_p2": "74,800",
                    "hgh_prc_p2": "75,300",
                    "lw_prc_p2": "74,700",
                    "cls_prc_p2": "75,200",
                    "vlm": "1,122,334"
                  }
                ]
              }
            }
            """), true));

        List<StockCandle> candles = provider.candles(
            new MarketDataRequest("005930", "KOSPI"),
            CandleInterval.DAILY,
            2
        );

        assertThat(candles).extracting(StockCandle::dateTime)
            .containsExactly(
                LocalDate.of(2026, 9, 21).atStartOfDay(),
                LocalDate.of(2026, 9, 22).atStartOfDay()
            );
        assertThat(candles.get(1).provider()).isEqualTo("KB");
        assertThat(candles.get(1).openPrice()).isEqualByComparingTo("75200");
        assertThat(candles.get(1).closePrice()).isEqualByComparingTo("75300");
        assertThat(candles.get(1).volume()).isEqualByComparingTo("1234567");
    }

    @Test
    @DisplayName("KB Provider는 설정이 켜진 국내 주식만 지원한다")
    void supportsOnlyEnabledDomesticStocks() throws Exception {
        KbMarketDataProvider provider = new KbMarketDataProvider(new FixtureKbClient(json("{}"), true));
        KbMarketDataProvider disabledProvider = new KbMarketDataProvider(new FixtureKbClient(json("{}"), false));

        assertThat(provider.supports(new MarketDataRequest("005930", "KOSPI"))).isTrue();
        assertThat(provider.supports(new MarketDataRequest("005930", "NASDAQ"))).isFalse();
        assertThat(provider.supports(new MarketDataRequest("", "KOSPI"))).isFalse();
        assertThat(disabledProvider.supports(new MarketDataRequest("005930", "KOSPI"))).isFalse();
    }

    private static JsonNode json(String value) throws Exception {
        return OBJECT_MAPPER.readTree(value);
    }

    private static class FixtureKbClient extends KbSecuritiesAccountClient {

        private final JsonNode currentPriceResponse;
        private final JsonNode candleResponse;
        private final boolean marketDataEnabled;

        FixtureKbClient(JsonNode currentPriceResponse, boolean marketDataEnabled) {
            this(currentPriceResponse, currentPriceResponse, marketDataEnabled);
        }

        FixtureKbClient(JsonNode currentPriceResponse, JsonNode candleResponse, boolean marketDataEnabled) {
            super(properties(), RestClient.builder().build());
            this.currentPriceResponse = currentPriceResponse;
            this.candleResponse = candleResponse;
            this.marketDataEnabled = marketDataEnabled;
        }

        @Override
        public boolean isMarketDataEnabled() {
            return marketDataEnabled;
        }

        @Override
        public JsonNode fetchCurrentPrice(String stockCode) {
            return currentPriceResponse;
        }

        @Override
        public JsonNode fetchCandles(String stockCode, String market, CandleInterval interval, int count) {
            return candleResponse;
        }

        private static SecuritiesProviderProperties properties() {
            SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
            Provider kb = new Provider();
            kb.setMarketDataEnabled(true);
            kb.setAppKey("app-key");
            kb.setAppSecret("app-secret");
            properties.setKb(kb);
            return properties;
        }
    }
}
