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
import com.sagopalgo.api.market.model.CandleInterval;
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
                  "dataHeader": {
                    "ipAddr": "127.0.0.1",
                    "macAddr": "00:00:00:00:00:00"
                  },
                  "dataBody": {
                    "appKey": "kb-app-key",
                    "appSecret": "kb-app-secret",
                    "grantType": "client_credentials"
                  }
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
                    "ipAddr": "192.0.2.10",
                    "macAddr": "AA-BB-CC-DD-EE-FF",
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
                    "ipAddr": "192.0.2.10",
                    "macAddr": "AA-BB-CC-DD-EE-FF",
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
    @DisplayName("조회 요청 IP와 MAC이 비어 있어도 두 필드를 빈 문자열로 보내 계좌 API를 호출한다")
    void fetchHoldingsSendsEmptyRequestDeviceAddresses() {
        SecuritiesProviderProperties properties = securitiesProperties();
        properties.getKb().setRequestIpAddress(" ");
        properties.getKb().setRequestMacAddress(null);
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer localServer = MockRestServiceServer.bindTo(builder).build();
        KbSecuritiesAccountClient localClient = new KbSecuritiesAccountClient(properties, builder.build());

        localServer.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {"access_token": "access-token", "expires_in": 3600}
                """, MediaType.APPLICATION_JSON));
        localServer.expect(requestTo("https://kb.test/api/v1/holdings"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "ipAddr": "",
                    "macAddr": "",
                    "tr_id": "HOLDINGS_TR",
                    "custtype": "P"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {"rt_cd": "0", "dataBody": {"Record1": []}}
                """, MediaType.APPLICATION_JSON));

        assertThat(localClient.items(localClient.fetchHoldings(), "Record1")).isEmpty();
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
            .hasMessage("KB증권 access token 발급 실패: 인증 정보를 확인할 수 없습니다. (status=401)")
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
            .hasMessage("KB증권 access token 응답 오류: API 권한이 없습니다.")
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    @Test
    @DisplayName("토큰 발급 요청은 설정값 앞뒤 공백을 제거해 전송한다")
    void fetchHoldingsTrimsTokenRequestCredentials() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer localServer = MockRestServiceServer.bindTo(builder).build();
        SecuritiesProviderProperties properties = securitiesProperties();
        properties.getKb().setGrantType(" client_credentials ");
        properties.getKb().setAppKey(" kb-app-key ");
        properties.getKb().setAppSecret(" kb-app-secret ");
        KbSecuritiesAccountClient localClient = new KbSecuritiesAccountClient(properties, builder.build());

        localServer.expect(requestTo("https://kb.test/oauth2/token"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "ipAddr": "127.0.0.1",
                    "macAddr": "00:00:00:00:00:00"
                  },
                  "dataBody": {
                    "appKey": "kb-app-key",
                    "appSecret": "kb-app-secret",
                    "grantType": "client_credentials"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        localServer.expect(requestTo("https://kb.test/api/v1/holdings"))
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
                    "ipAddr": "192.0.2.10",
                    "macAddr": "AA-BB-CC-DD-EE-FF",
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
                    "ipAddr": "192.0.2.10",
                    "macAddr": "AA-BB-CC-DD-EE-FF",
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

    @Test
    @DisplayName("현재가는 IVU10140 기본 요청값으로 호출한다")
    void fetchCurrentPriceCallsKbOpenApi() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ivu10140"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "custtype": "P"
                  },
                  "dataBody": {
                    "excg_clsf": "0",
                    "shrt_cd": "005930"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "rt_cd": "0",
                  "dataBody": {
                    "now_prc": "75300"
                  }
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchCurrentPrice("005930");

        assertThat(client.decimal(response, "now_prc")).isEqualByComparingTo("75300");
        server.verify();
    }

    @Test
    @DisplayName("통합차트는 IVS11560 데이터수 조회 요청값으로 호출한다")
    void fetchCandlesCallsKbOpenApi() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {
                  "access_token": "access-token",
                  "expires_in": 3600
                }
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ivs11560"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {
                    "custtype": "P"
                  },
                  "dataBody": {
                    "info_ccd": "2",
                    "mkt_clsf": "0",
                    "chrt_clsf": "W",
                    "minute_tck_indx": "",
                    "is_cd": "005930",
                    "inq_clsf": "2",
                    "strt_dy": "",
                    "inq_cnt": "20"
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "dataHeader": {"resultCode": "200", "processFlag": "A"},
                  "dataBody": {"out2": []}
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchCandles("005930", "KOSPI", CandleInterval.WEEKLY, 20);

        assertThat(client.items(response, "out2")).isEmpty();
        server.verify();
    }

    @Test
    @DisplayName("체결미체결 조회는 읽기 전용 SSQM2341과 다음키를 사용한다")
    void fetchOrderExecutionsUsesOfficialRequestFields() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {"access_token":"access-token","expires_in":3600}
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm2341"))
            .andExpect(method(HttpMethod.POST))
            .andExpect(header(HttpHeaders.AUTHORIZATION, "Bearer access-token"))
            .andExpect(content().json("""
                {
                  "dataHeader": {"custtype":"P"},
                  "dataBody": {
                    "ccls_clsf":"0",
                    "ordr_dt":"20260923",
                    "nxt_key":"CURSOR  "
                  }
                }
                """))
            .andRespond(withSuccess("""
                {
                  "dataHeader":{"resultCode":"200","processFlag":"A"},
                  "dataBody":{"nxt_key":"","Record1":[]}
                }
                """, MediaType.APPLICATION_JSON));

        JsonNode response = client.fetchOrderExecutions("20260923", "0", "CURSOR  ");

        assertThat(response.path("dataBody").path("Record1").isArray()).isTrue();
        server.verify();
    }

    @Test
    @DisplayName("KB가 조회 실패를 반환하면 빈 주문 목록으로 오인하지 않는다")
    void fetchOrderExecutionsRejectsBrokerFailure() {
        server.expect(requestTo("https://kb.test/oauth2/token"))
            .andRespond(withSuccess("""
                {"access_token":"access-token","expires_in":3600}
                """, MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm2341"))
            .andRespond(withSuccess("""
                {
                  "dataHeader":{"resultCode":"200","processFlag":"B","processMessage":"계좌 조회 실패"},
                  "dataBody":{"Record1":[]}
                }
                """, MediaType.APPLICATION_JSON));

        assertThatThrownBy(() -> client.fetchOrderExecutions("20260923", "0", ""))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.EXTERNAL_DATA_ERROR);
        server.verify();
    }

    private SecuritiesProviderProperties securitiesProperties() {
        SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
        Provider kb = new Provider();
        kb.setMarketDataEnabled(true);
        kb.setAccountEnabled(true);
        kb.setBaseUrl("https://kb.test");
        kb.setGrantType("client_credentials");
        kb.setTokenPath("/oauth2/token");
        kb.setHoldingsPath("/api/v1/holdings");
        kb.setSettlementBalancePath("/api/v1/ssqm2932");
        kb.setExecutionBalancePath("/api/v1/ssqm2952");
        kb.setCurrentPricePath("/api/v1/ivu10140");
        kb.setCandlePath("/api/v1/ivs11560");
        kb.setHoldingsTransactionId("HOLDINGS_TR");
        kb.setCustomerType("P");
        kb.setRequestIpAddress(" 192.0.2.10 ");
        kb.setRequestMacAddress(" AA-BB-CC-DD-EE-FF ");
        kb.setBalanceInquiryClassification("1");
        kb.setBalanceExchangeMarketPriceCode("A");
        kb.setCurrentPriceExchangeClassification("0");
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
