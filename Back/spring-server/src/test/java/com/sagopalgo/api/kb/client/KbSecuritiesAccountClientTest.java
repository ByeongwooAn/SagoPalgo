package com.sagopalgo.api.kb.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

/**
 * KB증권 Open API 계좌 클라이언트의 인증과 조회 계약을 검증합니다.
 */
class KbSecuritiesAccountClientTest {

    private MockRestServiceServer server;
    private KbSecuritiesAccountClient client;

    @BeforeEach
    void setUp() {
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        client = new KbSecuritiesAccountClient(securitiesProperties(), builder.build());
    }

    @Test
    @DisplayName("보유 주식 조회는 KB 토큰 발급 후 Bearer 토큰으로 잔고 TR을 호출한다")
    void fetchHoldingsCallsKbOpenApiWithBearerToken() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().json("""
                {
                  "grant_type": "client_credentials",
                  "appKey": "kb-app-key",
                  "appSecret": "kb-app-secret"
                }
                """))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/holdings"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "tr_id": "HOLDINGS_TR",
                    "custtype": "P"
                  },
                  "dataBody": {
                    "acct_no": "1234567890",
                    "acct_prdt_cd": "01"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "holdings": [
                      {
                        "stockCode": "005930",
                        "stockName": "삼성전자",
                        "quantity": "12",
                        "averageBuyPrice": "69100",
                        "currentPrice": "75300"
                      }
                    ]
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchHoldings();

        assertThat(client.items(response, "holdings")).hasSize(1);
        assertThat(client.text(response, "stockCode")).isEqualTo("005930");
        assertThat(client.decimal(response, "currentPrice")).isEqualByComparingTo("75300");
        server.verify();
    }

    @Test
    @DisplayName("계좌번호가 비어 있으면 보유 주식 조회 요청 body에 계좌 필드를 보내지 않는다")
    void fetchHoldingsAllowsMissingAccountNumber() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer localServer = MockRestServiceServer.bindTo(builder).build();
        KbSecuritiesAccountClient localClient = new KbSecuritiesAccountClient(
            securitiesPropertiesWithoutAccountNumber(),
            builder.build()
        );

        localServer.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        localServer.expect(requestTo("https://kb.test/api/v1/holdings"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "tr_id": "HOLDINGS_TR",
                    "custtype": "P"
                  },
                  "dataBody": {}
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "holdings": []
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = localClient.fetchHoldings();

        assertThat(localClient.items(response, "holdings")).isEmpty();
        localServer.verify();
    }

    @Test
    @DisplayName("KB 실패 코드는 외부 데이터 오류로 변환한다")
    void fetchHoldingsThrowsExternalDataErrorWhenKbFails() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/holdings"))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "1",
                  "msg1": "계좌 권한이 없습니다."
                }
                """, MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.fetchHoldings())
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    private SecuritiesProviderProperties securitiesProperties() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider kb = new Provider();
        kb.setAccountEnabled(true);
        kb.setBaseUrl("https://kb.test");
        kb.setGrantType("client_credentials");
        kb.setTokenPath("/oauth2/token");
        kb.setHoldingsPath("/api/v1/holdings");
        kb.setHoldingsTransactionId("HOLDINGS_TR");
        kb.setCustomerType("P");
        kb.setAppKey("kb-app-key");
        kb.setAppSecret("kb-app-secret");
        kb.setAccountNumber("1234567890");
        kb.setAccountProductCode("01");
        kb.setAccountNumberField("acct_no");
        kb.setAccountProductCodeField("acct_prdt_cd");
        properties.setKb(kb);
        return properties;
    }

    private SecuritiesProviderProperties securitiesPropertiesWithoutAccountNumber() {
        SecuritiesProviderProperties properties = securitiesProperties();
        properties.getKb().setAccountNumber("");
        properties.getKb().setAccountProductCode("");
        return properties;
    }
}
