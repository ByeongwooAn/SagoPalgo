package com.sagopalgo.api.kb.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
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
import org.springframework.http.HttpStatus;
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
                  "grantType": "client_credentials",
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
                    "inq_clsf": "0",
                    "mkt_tm_ccd": "1",
                    "acct_no": "1234567890",
                    "acct_prdt_cd": "01"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "Record1": [
                      {
                        "is_no": "005930",
                        "is_nm": "삼성전자",
                        "ordr_psbl_q": "12",
                        "gnrl_q": "12"
                      }
                    ]
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchHoldings();

        assertThat(client.items(response, "Record1")).hasSize(1);
        assertThat(client.text(response, "is_no")).isEqualTo("005930");
        assertThat(client.decimal(response, "gnrl_q")).isEqualByComparingTo("12");
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
                  "dataBody": {
                    "inq_clsf": "0",
                    "mkt_tm_ccd": "1"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "Record1": []
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = localClient.fetchHoldings();

        assertThat(localClient.items(response, "Record1")).isEmpty();
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

    @Test
    @DisplayName("토큰 발급 HTTP 실패는 외부 데이터 오류로 변환한다")
    void fetchHoldingsThrowsExternalDataErrorWhenTokenRequestFails() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withStatus(HttpStatus.UNAUTHORIZED)
                .contentType(MediaType.APPLICATION_JSON)
                .body("""
                    {
                      "rt_cd": "1",
                      "msg1": "인증 정보를 확인할 수 없습니다.",
                      "appKey": "echoed-app-key"
                    }
                    """));

        assertThatThrownBy(() -> client.fetchHoldings())
            .isInstanceOf(ApiException.class)
            .hasMessage("KB증권 access token 발급에 실패했습니다.")
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    @Test
    @DisplayName("토큰 발급 응답에 access token이 없으면 외부 데이터 오류로 변환한다")
    void fetchHoldingsThrowsExternalDataErrorWhenTokenResponseHasNoAccessToken() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "1",
                  "msg1": "API 권한이 없습니다."
                }
                """, MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.fetchHoldings())
            .isInstanceOf(ApiException.class)
            .hasMessage("KB증권 access token 응답이 올바르지 않습니다.")
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    @Test
    @DisplayName("결제기준 잔고 현황은 SSQM2932 기본 요청값으로 호출한다")
    void fetchSettlementBalanceCallsKbOpenApi() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm2932"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "custtype": "P"
                  },
                  "dataBody": {
                    "inq_clsf": "1",
                    "excg_mktpr_ccd": "A"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "val_amt_sum": "1130000",
                    "Record1": []
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchSettlementBalance();

        assertThat(client.decimal(response, "val_amt_sum")).isEqualByComparingTo("1130000");
        server.verify();
    }

    @Test
    @DisplayName("체결기준 잔고 현황은 SSQM2952 기본 요청값으로 호출한다")
    void fetchExecutionBalanceCallsKbOpenApi() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm2952"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "custtype": "P"
                  },
                  "dataBody": {
                    "excg_mktpr_ccd": "A"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "nt_asts_val_amt": "1500000",
                    "Record1": []
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchExecutionBalance();

        assertThat(client.decimal(response, "nt_asts_val_amt")).isEqualByComparingTo("1500000");
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
        kb.setSettlementBalancePath("/api/v1/ssqm2932");
        kb.setExecutionBalancePath("/api/v1/ssqm2952");
        kb.setHoldingsTransactionId("HOLDINGS_TR");
        kb.setCustomerType("P");
        kb.setBalanceInquiryClassification("1");
        kb.setBalanceExchangeMarketPriceCode("A");
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
