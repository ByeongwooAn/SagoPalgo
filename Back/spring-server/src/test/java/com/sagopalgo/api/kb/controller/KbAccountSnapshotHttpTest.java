package com.sagopalgo.api.kb.controller;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.service.KbAccountSnapshotService;
import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.match.MockRestRequestMatchers;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.client.RestClient;

/** 실제 controller→service→HTTP 직렬화 경로. Mock 서버 외의 KB·DB에 접속하지 않습니다. */
class KbAccountSnapshotHttpTest {
    private final SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
    private MockRestServiceServer server;
    private KbSecuritiesAccountClient client;
    private MockMvc mvc;

    @BeforeEach
    void setup() {
        var kb = properties.getKb();
        kb.setBaseUrl("https://kb.test");
        kb.setTokenPath("/oauth2/token");
        kb.setAppKey("private-key");
        kb.setAppSecret("private-secret");
        kb.setAccountNumber("private-account");
        kb.setAccountEnabled(true);
        kb.setHoldingsPath("/api/v1/ssqm1801");
        kb.setSettlementBalancePath("/api/v1/ssqm2932");
        kb.setExecutionBalancePath("/api/v1/ssqm2952");
        RestClient.Builder builder = RestClient.builder();
        server = MockRestServiceServer.bindTo(builder).build();
        client = new KbSecuritiesAccountClient(properties, builder.build());
        mvc = MockMvcBuilders.standaloneSetup(new KbAccountSnapshotController(
            new KbAccountSnapshotService(client, properties)))
            .setControllerAdvice(new GlobalExceptionHandler()).build();
    }

    @Test
    void readOnlyHttpFlowFollowsCursorKeepsDecimalsAndDisablesCaching() throws Exception {
        server.expect(requestTo("https://kb.test/oauth2/token")).andRespond(withSuccess(
            "{\"access_token\":\"private-token\",\"expires_in\":3600}", MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm1801"))
            .andExpect(method(HttpMethod.POST)).andExpect(MockRestRequestMatchers.jsonPath("$.dataBody.nxt_key").doesNotExist())
            .andRespond(withSuccess(ok("""
                {"Record1":[{"is_no":"005930","gnrl_q":"1","accountNumber":"private-account"}],"nxt_key":"next  "}
                """), MediaType.APPLICATION_JSON));
        server.expect(requestTo("https://kb.test/api/v1/ssqm1801"))
            .andExpect(method(HttpMethod.POST)).andExpect(MockRestRequestMatchers.jsonPath("$.dataBody.nxt_key").value("next  "))
            .andRespond(withSuccess(ok("""
                {"Record1":[],"nxt_key":""}
                """), MediaType.APPLICATION_JSON));
        expect("ssqm2932", "{\"Record1\":[],\"tl_data_cnt\":\"0\",\"ordr_psbl_csh\":\"1234.560000\"}");
        expect("ssqm2952", """
            {"Record1":[{"is_cd":"005930","hld_q_p6":"0.123456"}],"tl_data_cnt":"1"}
            """);
        server.expect(requestTo("https://kb.test/api/v1/ssqm2341"))
            .andExpect(method(HttpMethod.POST)).andExpect(MockRestRequestMatchers.jsonPath("$.dataBody.ordr_dt").value("20261102"))
            .andExpect(MockRestRequestMatchers.jsonPath("$.dataBody.ccls_clsf").value("0"))
            .andRespond(withSuccess(ok("{\"ordr_dt\":\"20261102\",\"Record1\":[],\"nxt_key\":\"\"}"), MediaType.APPLICATION_JSON));
        var response = mvc.perform(get("/api/v1/kb/accounts/primary/snapshot").param("orderDate", "20261102"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control", "no-store"))
            .andExpect(jsonPath("$.data.status").value("SUCCESS"))
            .andExpect(jsonPath("$.data.usableForTrading").value(false))
            .andExpect(jsonPath("$.data.atomic").value(false))
            .andExpect(jsonPath("$.data.sections[0].pagesRead").value(2))
            .andExpect(jsonPath("$.data.sections[1].summary.ordr_psbl_csh").value("1234.560000"))
            .andExpect(jsonPath("$.data.sections[2].rows[0].fields.hld_q_p6").value("0.123456"))
            .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(response).doesNotContain("private-key", "private-secret", "private-account", "private-token");
        JsonNode json = new ObjectMapper().readTree(response);
        assertThat(json.path("data").path("sections").get(2).path("rows").get(0).path("fields").get("now_prc").isNull()).isTrue();
        server.verify();
    }

    @Test
    void disabledSnapshotReturnsWithoutTokenOrBrokerRequests() throws Exception {
        properties.getKb().setAccountEnabled(false);
        mvc.perform(get("/api/v1/kb/accounts/primary/snapshot"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.status").value("DISABLED"));
        server.verify();
    }

    @Test
    void invalidDateIsAnHttp400BeforeAuthentication() throws Exception {
        mvc.perform(get("/api/v1/kb/accounts/primary/snapshot").param("orderDate", "20260230"))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        server.verify();
    }

    @ParameterizedTest
    @ValueSource(strings = {"1234567890123", "bad\nkey", "\n"})
    void invalidHoldingsCursorDoesNotMakeAnyHttpRequest(String cursor) {
        assertThatThrownBy(() -> client.fetchHoldingsPage(cursor)).isInstanceOf(RuntimeException.class);
        server.verify();
    }

    private void expect(String api, String body) {
        server.expect(requestTo("https://kb.test/api/v1/" + api)).andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(ok(body), MediaType.APPLICATION_JSON));
    }

    private String ok(String body) {
        return "{\"dataHeader\":{\"resultCode\":\"200\",\"processFlag\":\"A\",\"processTime\":\"20261102003000000\"},\"dataBody\":" + body + "}";
    }
}
