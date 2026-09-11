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
import java.math.BigDecimal;
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
    @DisplayName("국내 주식 현재가는 KIS 토큰 발급 후 주식현재가 시세 API에서 조회한다")
    void currentPriceFetchesDomesticStockPrice() {
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
                    "prdy_vrss": "100"
                  }
                }
                """, MediaType.APPLICATION_JSON));

        BigDecimal currentPrice = client.currentPrice(holding("005930", "KOSPI"));

        assertThat(currentPrice).isEqualByComparingTo("75300");
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
