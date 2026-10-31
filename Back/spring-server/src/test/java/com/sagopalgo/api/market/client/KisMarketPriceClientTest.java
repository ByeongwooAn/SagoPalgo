package com.sagopalgo.api.market.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
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
 * 한국투자증권 현재가 클라이언트의 외부 API 계약을 검증합니다.
 */
class KisMarketPriceClientTest {

    private MockRestServiceServer server;
    private KisMarketPriceClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        client = new KisMarketPriceClient(kisProperties(), builder.build());
    }

    @Test
    @DisplayName("국내 주식 시세는 KIS 토큰 발급 후 내부 표준 모델로 정규화한다")
    void quoteFetchesDomesticStockPrice() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=005930"))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(header("appkey", "app-key"))
            .andExpect(header("appsecret", "app-secret"))
            .andExpect(header("tr_id", "FHKST01010100"))
            .andExpect(header("custtype", "P"))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "msg1": "정상처리 되었습니다.",
                  "output": {
                    "stck_prpr": "75300",
                    "prdy_vrss": "100",
                    "prdy_ctrt": "0.13",
                    "acml_vol": "1234567",
                    "stck_oprc": "75200",
                    "stck_hgpr": "75500",
                    "stck_lwpr": "74900",
                    "stck_sdpr": "75200"
                  }
                }
                """, MediaType.APPLICATION_JSON));

        StockQuote quote = client.quote(new MarketDataRequest("005930", "KOSPI"));

        assertThat(quote.provider()).isEqualTo("KIS");
        assertThat(quote.currentPrice()).isEqualByComparingTo("75300");
        assertThat(quote.changePrice()).isEqualByComparingTo("100");
        assertThat(quote.changeRate()).isEqualByComparingTo("0.13");
        assertThat(quote.volume()).isEqualByComparingTo("1234567");
        assertThat(quote.openPrice()).isEqualByComparingTo("75200");
        assertThat(quote.highPrice()).isEqualByComparingTo("75500");
        assertThat(quote.lowPrice()).isEqualByComparingTo("74900");
        assertThat(quote.previousClose()).isEqualByComparingTo("75200");
        server.verify();
    }

    @Test
    @DisplayName("국내 주식 기간별 시세를 시간 오름차순 표준 캔들로 변환한다")
    void candlesFetchDomesticStockHistory() {
        LocalDate endDate = LocalDate.now(ZoneId.of("Asia/Seoul"));
        LocalDate startDate = endDate.minusDays(34);
        DateTimeFormatter formatter = DateTimeFormatter.BASIC_ISO_DATE;

        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo(
                "https://kis.test/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
                    + "?FID_COND_MRKT_DIV_CODE=J"
                    + "&FID_INPUT_ISCD=005930"
                    + "&FID_INPUT_DATE_1=" + startDate.format(formatter)
                    + "&FID_INPUT_DATE_2=" + endDate.format(formatter)
                    + "&FID_PERIOD_DIV_CODE=D"
                    + "&FID_ORG_ADJ_PRC=0"
            ))
            .andExpect(method(HttpMethod.GET))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(header("tr_id", "FHKST03010100"))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "msg1": "정상처리 되었습니다.",
                  "output2": [
                    {
                      "stck_bsop_date": "20260922",
                      "stck_oprc": "75200",
                      "stck_hgpr": "75500",
                      "stck_lwpr": "74900",
                      "stck_clpr": "75300",
                      "acml_vol": "1234567"
                    },
                    {
                      "stck_bsop_date": "20260921",
                      "stck_oprc": "74800",
                      "stck_hgpr": "75300",
                      "stck_lwpr": "74700",
                      "stck_clpr": "75200",
                      "acml_vol": "1122334"
                    }
                  ]
                }
                """, MediaType.APPLICATION_JSON));

        List<StockCandle> candles = client.candles(
            new MarketDataRequest("005930", "KOSPI"),
            CandleInterval.DAILY,
            2
        );

        assertThat(candles).extracting(StockCandle::provider).containsOnly("KIS");
        assertThat(candles).extracting(StockCandle::dateTime)
            .containsExactly(
                LocalDate.of(2026, 9, 21).atStartOfDay(),
                LocalDate.of(2026, 9, 22).atStartOfDay()
            );
        assertThat(candles.get(1).openPrice()).isEqualByComparingTo("75200");
        assertThat(candles.get(1).closePrice()).isEqualByComparingTo("75300");
        assertThat(candles.get(1).volume()).isEqualByComparingTo("1234567");
        server.verify();
    }

    @Test
    @DisplayName("KIS가 실패 코드를 반환하면 외부 데이터 오류로 변환한다")
    void currentPriceThrowsExternalDataErrorWhenKisFails() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=005930"))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "1",
                  "msg1": "조회 가능한 종목이 아닙니다."
                }
                """, MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.currentPrice(holding("005930", "KOSPI")))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    @Test
    @DisplayName("KIS 클라이언트는 설정이 켜진 국내 주식만 지원한다")
    void supportsOnlyEnabledDomesticStocks() {
        assertThat(client.supports(holding("005930", "KOSPI"))).isTrue();
        assertThat(client.supports(holding("005930", "NASDAQ"))).isFalse();
        assertThat(client.supports(holding("", "KOSPI"))).isFalse();
    }

    @Test
    void kospiUsesOfficialIndexContractSortsDatesAndCachesOneRequest() {
        LocalDate today = LocalDate.now(ZoneId.of("Asia/Seoul"));
        var format = DateTimeFormatter.BASIC_ISO_DATE;
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("{\"access_token\":\"index-token\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice"
            + "?FID_COND_MRKT_DIV_CODE=U&FID_INPUT_ISCD=0001&FID_INPUT_DATE_1=" + today.minusDays(45).format(format)
            + "&FID_INPUT_DATE_2=" + today.format(format) + "&FID_PERIOD_DIV_CODE=D"))
            .andExpect(method(HttpMethod.GET)).andExpect(header("tr_id", "FHKUP03500100"))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer index-token"))
            .andRespond(withSuccess("""
                {"rt_cd":"0","output1":{"bstp_nmix_prpr":"3,020.5","bstp_nmix_prdy_ctrt":"-0.25"},
                 "output2":[{"stck_bsop_date":"%s","bstp_nmix_prpr":"3020"},
                   {"stck_bsop_date":"%s","bstp_nmix_prpr":"3000"},
                   {"stck_bsop_date":"","bstp_nmix_prpr":"0"}]}
                """.formatted(today.minusDays(1).format(format), today.minusDays(2).format(format)), MediaType.APPLICATION_JSON));
        var result = client.kospi();
        assertThat(result.status()).isEqualTo("SUCCESS");
        assertThat(result.value()).isEqualByComparingTo("3020.5");
        assertThat(result.changeRate()).isEqualByComparingTo("-0.25");
        assertThat(result.points()).hasSize(2);
        assertThat(result.points().get(0).date()).isEqualTo(today.minusDays(2));
        assertThat(result.receivedAt()).isNotNull();
        assertThat(client.kospi()).isSameAs(result);
        server.verify();
    }

    @Test
    void indexApiFailureIsCachedWithoutFakePricesOrSecretErrorText() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("{\"access_token\":\"index-token\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-daily-indexchartprice"))
            .andRespond(withSuccess("{\"rt_cd\":\"1\",\"msg1\":\"private-app-secret\"}", MediaType.APPLICATION_JSON));
        var result = client.kospi();
        assertThat(result.status()).isEqualTo("FAILED");
        assertThat(result.value()).isNull();
        assertThat(result.points()).isEmpty();
        assertThat(result.toString()).doesNotContain("private-app-secret");
        assertThat(client.kospi()).isSameAs(result);
        server.verify();
    }

    @Test
    void disabledIndexDoesNotIssueTokens() {
        var disabled = new KisMarketPriceClient(new KisMarketProperties(), RestClient.create());
        assertThat(disabled.kospi().status()).isEqualTo("DISABLED");
        assertThat(disabled.kospi().receivedAt()).isNull();
    }

    private KisMarketProperties kisProperties() {
        KisMarketProperties properties = new KisMarketProperties();
        properties.setEnabled(true);
        properties.setBaseUrl("https://kis.test");
        properties.setAppKey("app-key");
        properties.setAppSecret("app-secret");
        properties.setGrantType("client_credentials");
        properties.setTokenPath("/oauth2/tokenP");
        properties.setPricePath("/uapi/domestic-stock/v1/quotations/inquire-price");
        properties.setTransactionId("FHKST01010100");
        properties.setCandlePath("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice");
        properties.setCandleTransactionId("FHKST03010100");
        properties.setCustomerType("P");
        return properties;
    }

    private Holding holding(String stockCode, String market) {
        Holding holding = new Holding();
        holding.setStockCode(stockCode);
        holding.setMarket(market);
        holding.setBuyPrice(new BigDecimal("69100"));
        return holding;
    }
}
