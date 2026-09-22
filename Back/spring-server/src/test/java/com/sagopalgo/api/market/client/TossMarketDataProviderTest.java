package com.sagopalgo.api.market.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockInfo;
import com.sagopalgo.api.market.model.StockQuote;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/**
 * 토스증권 공식 Open API 요청과 응답 매핑 계약을 검증합니다.
 */
class TossMarketDataProviderTest {

    private MockRestServiceServer server;
    private TossMarketDataProvider provider;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        provider = new TossMarketDataProvider(properties(), builder.build());
    }

    @Test
    @DisplayName("OAuth 토큰을 발급받아 공식 현재가 응답을 표준 시세로 변환한다")
    void quoteUsesOAuthTokenAndMapsOfficialPriceResponse() {
        expectToken();
        server.expect(requestTo("https://toss.test/api/v1/prices?symbols=005930"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer toss-token"))
            .andRespond(withSuccess("""
                {
                  "result": [
                    {
                      "symbol": "005930",
                      "timestamp": "2026-09-23T09:30:00.123+09:00",
                      "lastPrice": "72000",
                      "currency": "KRW"
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        StockQuote quote = provider.quote(new MarketDataRequest("005930", "KOSPI"));

        assertThat(quote.provider()).isEqualTo("TOSS");
        assertThat(quote.currentPrice()).isEqualByComparingTo("72000");
        assertThat(quote.changeRate()).isZero();
        assertThat(quote.receivedAt()).isEqualTo(Instant.parse("2026-09-23T00:30:00.123Z"));
        server.verify();
    }

    @Test
    @DisplayName("토스 일봉을 시간 오름차순 표준 캔들로 변환한다")
    void candlesMapsOfficialDailyCandleResponse() {
        expectToken();
        server.expect(requestTo(
                "https://toss.test/api/v1/candles?symbol=005930&interval=1d&count=2&adjusted=true"
            ))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer toss-token"))
            .andRespond(withSuccess("""
                {
                  "result": {
                    "candles": [
                      {
                        "timestamp": "2026-09-23T00:00:00+09:00",
                        "openPrice": "71600",
                        "highPrice": "72300",
                        "lowPrice": "71500",
                        "closePrice": "72000",
                        "volume": "3521000",
                        "currency": "KRW"
                      },
                      {
                        "timestamp": "2026-09-22T00:00:00+09:00",
                        "openPrice": "71200",
                        "highPrice": "71800",
                        "lowPrice": "71000",
                        "closePrice": "71600",
                        "volume": "2984000",
                        "currency": "KRW"
                      }
                    ],
                    "nextBefore": "2026-09-22T00:00:00+09:00"
                  }
                }
                """, MediaType.APPLICATION_JSON));

        List<StockCandle> candles = provider.candles(
            new MarketDataRequest("005930", "KOSPI"),
            CandleInterval.DAILY,
            2
        );

        assertThat(candles).extracting(StockCandle::dateTime)
            .containsExactly(
                LocalDateTime.of(2026, 9, 22, 0, 0),
                LocalDateTime.of(2026, 9, 23, 0, 0)
            );
        assertThat(candles.get(1).closePrice()).isEqualByComparingTo("72000");
        assertThat(candles.get(1).volume()).isEqualByComparingTo("3521000");
        server.verify();
    }

    @Test
    @DisplayName("공식 종목 기본 정보를 내부 종목 모델로 변환한다")
    void stockInfoMapsOfficialResponse() {
        expectToken();
        server.expect(requestTo("https://toss.test/api/v1/stocks?symbols=005930"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer toss-token"))
            .andRespond(withSuccess("""
                {
                  "result": [
                    {
                      "symbol": "005930",
                      "name": "삼성전자",
                      "englishName": "SamsungElec",
                      "market": "KOSPI",
                      "securityType": "STOCK",
                      "isCommonShare": true,
                      "status": "ACTIVE",
                      "currency": "KRW",
                      "listDate": "1975-06-11",
                      "delistDate": null,
                      "sharesOutstanding": "5919637922",
                      "koreanMarketDetail": {
                        "nxtSupported": true,
                        "krxTradingSuspended": false,
                        "nxtTradingSuspended": false
                      }
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        StockInfo info = provider.stockInfo(new MarketDataRequest("005930", "KOSPI"))
            .orElseThrow();

        assertThat(info.provider()).isEqualTo("TOSS");
        assertThat(info.stockName()).isEqualTo("삼성전자");
        assertThat(info.market()).isEqualTo("KOSPI");
        assertThat(info.listedAt()).isEqualTo(LocalDate.of(1975, 6, 11));
        assertThat(info.sharesOutstanding()).isEqualByComparingTo("5919637922");
        assertThat(info.nxtSupported()).isTrue();
        assertThat(info.tradingSuspended()).isFalse();
        server.verify();
    }

    @Test
    @DisplayName("설정이 켜진 국내와 미국 종목을 지원한다")
    void supportsDomesticAndUsStocks() {
        assertThat(provider.supports(new MarketDataRequest("005930", "KOSPI"))).isTrue();
        assertThat(provider.supports(new MarketDataRequest("AAPL", "NASDAQ"))).isTrue();
        assertThat(provider.supports(new MarketDataRequest("BTC", "CRYPTO"))).isFalse();
        assertThat(provider.supports(new MarketDataRequest("", "KOSPI"))).isFalse();
    }

    @Test
    @DisplayName("공식 지원 범위가 아닌 주봉과 월봉은 임의 합성하지 않는다")
    void doesNotSynthesizeUnsupportedCandleIntervals() {
        MarketDataRequest request = new MarketDataRequest("005930", "KOSPI");

        assertThat(provider.candles(request, CandleInterval.WEEKLY, 10)).isEmpty();
        assertThat(provider.candles(request, CandleInterval.MONTHLY, 10)).isEmpty();
    }

    private void expectToken() {
        server.expect(requestTo("https://toss.test/oauth2/token"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_FORM_URLENCODED_VALUE))
            .andExpect(content().string(
                "grant_type=client_credentials&client_id=toss-client-id&client_secret=toss-client-secret"
            ))
            .andRespond(withSuccess("""
                {
                  "access_token": "toss-token",
                  "token_type": "Bearer",
                  "expires_in": 86400
                }
                """, MediaType.APPLICATION_JSON));
    }

    private SecuritiesProviderProperties properties() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider toss = new Provider();
        toss.setMarketDataEnabled(true);
        toss.setBaseUrl("https://toss.test");
        toss.setGrantType("client_credentials");
        toss.setTokenPath("/oauth2/token");
        toss.setCurrentPricePath("/api/v1/prices");
        toss.setCandlePath("/api/v1/candles");
        toss.setStockInfoPath("/api/v1/stocks");
        toss.setAppKey("toss-client-id");
        toss.setAppSecret("toss-client-secret");
        properties.setToss(toss);
        return properties;
    }
}
