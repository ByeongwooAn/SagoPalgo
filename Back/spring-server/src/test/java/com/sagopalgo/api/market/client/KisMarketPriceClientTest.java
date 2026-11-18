package com.sagopalgo.api.market.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import java.math.BigDecimal;
import java.net.SocketTimeoutException;
import java.net.UnknownHostException;
import java.net.ConnectException;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.ResourceAccessException;
import javax.net.ssl.SSLHandshakeException;

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
    void usQuoteAndDailyCandlesUseOverseasTransactions() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("""
                {"access_token":"access-token","expires_in":3600}
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/overseas-price/v1/quotations/price?AUTH=&EXCD=AMS&SYMB=SPY"))
            .andExpect(header("tr_id", "HHDFS00000300"))
            .andRespond(withSuccess("""
                {"rt_cd":"0","output":{"last":"651.125","base":"650.00","tvol":"43"}}
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/overseas-price/v1/quotations/dailyprice?AUTH=&EXCD=AMS&SYMB=SPY&GUBN=0&BYMD=&MODP=0"))
            .andExpect(header("tr_id", "HHDFS76240000"))
            .andRespond(withSuccess("""
                {"rt_cd":"0","output2":[{"xymd":"20261113","open":"650.5","high":"652.0","low":"650.0","clos":"651.125","tvol":"1000"}]}
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/overseas-price/v1/quotations/search-info?PRDT_TYPE_CD=529&PDNO=SPY"))
            .andExpect(header("tr_id", "CTPF1702R"))
            .andRespond(withSuccess("""
                {"rt_cd":"0","output":{"prdt_eng_name":"SPDR S&P 500 ETF TRUST","tr_crcy_cd":"USD","lstg_yn":"Y"}}
                """, MediaType.APPLICATION_JSON));

        MarketDataRequest request = new MarketDataRequest("SPY", "AMEX");
        assertThat(client.quote(request).currentPrice()).isEqualByComparingTo("651.125");
        assertThat(client.candles(request, CandleInterval.DAILY, 60)).singleElement().satisfies(candle -> {
            assertThat(candle.closePrice()).isEqualByComparingTo("651.125");
            assertThat(candle.dateTime()).isEqualTo(LocalDate.of(2026, 11, 13).atStartOfDay());
        });
        assertThat(client.stockInfo(request).orElseThrow().currency()).isEqualTo("USD");
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
    void dailyModelUsesKrxRawPriceFlagsForBothEndpoints() {
        LocalDate date = LocalDate.of(2026, 11, 18);
        MarketDataRequest request = new MarketDataRequest("005930", "KOSPI");
        String row = """
            {"stck_bsop_date":"20261118","stck_oprc":"100","stck_hgpr":"110","stck_lwpr":"95",
             "stck_clpr":"105","acml_vol":"5000","mod_yn":"N","prtt_rate":"0.00"}
            """;
        String chart = "https://kis.test/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
            + "?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=005930&FID_INPUT_DATE_1=20261118"
            + "&FID_INPUT_DATE_2=20261118&FID_PERIOD_DIV_CODE=D&FID_ORG_ADJ_PRC=1";
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("{\"access_token\":\"token\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
        server.expect(requestTo(chart)).andRespond(withSuccess(
            "{\"rt_cd\":\"0\",\"output1\":{\"stck_shrn_iscd\":\"005930\"},\"output2\":[" + row + "]}",
            MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/inquire-daily-price"
                + "?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=005930&FID_PERIOD_DIV_CODE=D&FID_ORG_ADJ_PRC=0"))
            .andExpect(header("tr_id", "FHKST01010400"))
            .andRespond(withSuccess("{\"rt_cd\":\"0\",\"output\":[" + row + "]}", MediaType.APPLICATION_JSON));
        server.expect(requestTo(chart)).andRespond(withSuccess(
            "{\"rt_cd\":\"0\",\"output1\":{\"stck_shrn_iscd\":\"005930\"},\"output2\":["
                + row.replace("\"N\"", "\"Y\"") + "]}", MediaType.APPLICATION_JSON));

        assertThat(client.rawDailyCandles(request, date, date)).containsExactly(client.rawDailyReference(request, date).orElseThrow());
        assertThatThrownBy(() -> client.rawDailyCandles(request, date, date)).isInstanceOf(ApiException.class);
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

    @Test
    void httpFailureRetainsStatusAndKisCodeWithoutResponseBodyOrCredentials() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON).body("""
                {"msg_cd":"EGW00201","msg1":"private-app-secret access-token", "appkey":"app-key"}
                """));

        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("stage=QUOTE httpStatus=403 kisCode=EGW00201")
            .hasMessageNotContaining("private-app-secret")
            .hasMessageNotContaining("access-token")
            .hasMessageNotContaining("app-key")
            .hasMessageNotContaining("https://");
        server.verify();
    }

    @Test
    void tokenHttpFailureIdentifiesTokenStageWithoutAttemptingPriceRequest() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withStatus(HttpStatus.UNAUTHORIZED).contentType(MediaType.APPLICATION_JSON)
                .body("{\"error_code\":\"EGW00123\",\"error_description\":\"private-app-secret\"}"));
        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .hasMessageContaining("stage=TOKEN httpStatus=401 kisCode=EGW00123")
            .hasMessageNotContaining("private-app-secret");
        server.verify();
    }

    @Test
    void nonJsonHttpFailureKeepsStatusWithoutCopyingUpstreamPage() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withStatus(HttpStatus.BAD_GATEWAY).contentType(MediaType.TEXT_HTML)
                .body("<html>private-app-secret</html>"));
        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .hasMessageContaining("httpStatus=502 kisCode=UNAVAILABLE")
            .hasMessageNotContaining("private-app-secret");
        server.verify();
    }

    @Test
    void rejectsUnstructuredErrorCodesInsteadOfLoggingArbitraryText() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withStatus(HttpStatus.INTERNAL_SERVER_ERROR).contentType(MediaType.APPLICATION_JSON)
                .body("{\"msg_cd\":\"private-app-secret\\nforged log line\",\"msg1\":\"access-token\"}"));
        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .hasMessageContaining("httpStatus=500 kisCode=UNAVAILABLE")
            .hasMessageNotContaining("private-app-secret")
            .hasMessageNotContaining("forged")
            .hasMessageNotContaining("access-token");
        server.verify();
    }

    @Test
    void businessFailureRetainsCodesWithoutUpstreamMessageText() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withSuccess("{\"rt_cd\":\"1\",\"msg_cd\":\"OPSQ0002\",\"msg1\":\"private-app-secret\"}",
                MediaType.APPLICATION_JSON));
        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .hasMessageContaining("stage=QUOTE httpStatus=200 rt_cd=1 kisCode=OPSQ0002")
            .hasMessageNotContaining("private-app-secret");
        server.verify();
    }

    @Test
    void priceTimeoutIsConvertedToSafeDiagnostic() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withException(new SocketTimeoutException("private-app-secret")));
        assertThatThrownBy(() -> client.quote(new MarketDataRequest("000660", "KOSPI")))
            .hasMessageContaining("stage=QUOTE kind=TIMEOUT")
            .hasMessageNotContaining("private-app-secret");
        server.verify();
    }

    @Test
    void transportDiagnosticsDistinguishDnsTlsAndConnectionWithoutCauseText() {
        List<java.io.IOException> causes = List.of(new UnknownHostException("private-host"),
            new SSLHandshakeException("private-certificate"), new ConnectException("private-host"));
        List<String> kinds = List.of("DNS", "TLS", "CONNECT");
        for (int index = 0; index < causes.size(); index++) {
            ApiException failure = KisApiErrors.requestFailure("QUOTE", "현재가",
                new ResourceAccessException("private-url", causes.get(index)));
            assertThat(failure.getErrorCode()).isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
            assertThat(failure.getMessage()).contains("kind=" + kinds.get(index))
                .doesNotContain("private-host", "private-certificate", "private-url");
            assertThat(failure.getCause()).isNull();
        }
    }

    @Test
    void stockIdentityUsesOfficialProductInfoWithoutInventingMarketFromRequest() {
        expectToken();
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/search-stock-info?PRDT_TYPE_CD=300&PDNO=000660"))
            .andExpect(header("tr_id", "CTPF1002R"))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andRespond(withSuccess("""
                {"rt_cd":"0","output":{"pdno":"000660","prdt_abrv_name":"SK하이닉스",
                 "scts_mket_lstg_dt":"19961226","scts_mket_lstg_abol_dt":"00000000"}}
                """, MediaType.APPLICATION_JSON));
        var identity = client.domesticStockIdentity("000660").orElseThrow();
        assertThat(identity.stockCode()).isEqualTo("000660");
        assertThat(identity.stockName()).isEqualTo("SK하이닉스");
        assertThat(identity.market()).isEqualTo("KOSPI");
        assertThat(identity.provider()).isEqualTo("KIS");
        server.verify();
    }

    @Test
    void stockIdentityUsesCurrentListingRatherThanFormerMarket() {
        expectToken();
        expectIdentity("000001", """
            {"pdno":"000001","prdt_name":"테스트 종목","scts_mket_lstg_dt":"19960101",
            "scts_mket_lstg_abol_dt":"20000101","kosdaq_mket_lstg_dt":"20010101"}
            """);
        assertThat(client.domesticStockIdentity("000001").orElseThrow().market()).isEqualTo("KOSDAQ");
        server.verify();
    }

    @Test
    void missingListingDatesUseExplicitQuoteMarketAndMatchingSymbol() {
        expectToken();
        expectIdentity("000001", "{\"pdno\":\"000001\",\"prdt_abrv_name\":\"테스트 종목\"}");
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/inquire-price?FID_COND_MRKT_DIV_CODE=J&FID_INPUT_ISCD=000001"))
            .andRespond(withSuccess("{\"rt_cd\":\"0\",\"output\":{\"stck_shrn_iscd\":\"000001\",\"rprs_mrkt_kor_name\":\"코넥스\"}}", MediaType.APPLICATION_JSON));
        assertThat(client.domesticStockIdentity("000001").orElseThrow().market()).isEqualTo("KONEX");
        server.verify();
    }

    @Test
    void identityRejectsDifferentProductInsteadOfFillingWrongName() {
        expectToken();
        expectIdentity("000660", "{\"pdno\":\"005930\",\"prdt_abrv_name\":\"다른 종목\",\"scts_mket_lstg_dt\":\"19960101\"}");
        assertThatThrownBy(() -> client.domesticStockIdentity("000660")).isInstanceOf(ApiException.class)
            .hasMessageContaining("종목코드가 일치하지");
        server.verify();
    }

    @Test
    void unknownMarketIsNotDefaultedToKospi() {
        expectToken();
        expectIdentity("000001", "{\"pdno\":\"000001\",\"prdt_abrv_name\":\"테스트 종목\"}");
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("inquire-price"))
            .andRespond(withSuccess("{\"rt_cd\":\"0\",\"output\":{\"stck_shrn_iscd\":\"000001\",\"rprs_mrkt_kor_name\":\"알 수 없음\"}}", MediaType.APPLICATION_JSON));
        assertThatThrownBy(() -> client.domesticStockIdentity("000001")).hasMessageContaining("상장 시장을 확인할 수 없습니다");
        server.verify();
    }

    @Test
    void delistedIdentityIsRejected() {
        expectToken();
        expectIdentity("000001", "{\"pdno\":\"000001\",\"prdt_abrv_name\":\"테스트 종목\",\"lstg_abol_dt\":\"20000101\"}");
        assertThatThrownBy(() -> client.domesticStockIdentity("000001")).hasMessageContaining("상장폐지");
        server.verify();
    }

    @Test
    void identityHttpErrorRetainsSafeDiagnostics() {
        expectToken();
        server.expect(request -> assertThat(request.getURI().getPath()).endsWith("search-stock-info"))
            .andRespond(withStatus(HttpStatus.FORBIDDEN).contentType(MediaType.APPLICATION_JSON)
                .body("{\"msg_cd\":\"EGW00123\",\"msg1\":\"private-app-secret\"}"));
        assertThatThrownBy(() -> client.domesticStockIdentity("000660"))
            .hasMessageContaining("stage=STOCK_INFO httpStatus=403 kisCode=EGW00123")
            .hasMessageNotContaining("private-app-secret");
        server.verify();
    }

    @Test
    void disabledIdentityDoesNotCallProvider() {
        var disabled = new KisMarketPriceClient(new KisMarketProperties(), RestClient.create());
        assertThat(disabled.domesticStockIdentity("000660")).isEmpty();
    }

    private void expectIdentity(String code, String output) {
        server.expect(requestTo("https://kis.test/uapi/domestic-stock/v1/quotations/search-stock-info?PRDT_TYPE_CD=300&PDNO=" + code))
            .andRespond(withSuccess("{\"rt_cd\":\"0\",\"output\":" + output + "}", MediaType.APPLICATION_JSON));
    }

    private void expectToken() {
        server.expect(requestTo("https://kis.test/oauth2/tokenP"))
            .andRespond(withSuccess("{\"access_token\":\"access-token\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
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
