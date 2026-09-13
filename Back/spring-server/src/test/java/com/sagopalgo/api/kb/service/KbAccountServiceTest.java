package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbBalanceResponse;
import com.sagopalgo.api.kb.dto.KbHoldingsResponse;
import java.math.BigDecimal;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

/**
 * KB증권 계좌 서비스의 평가금액, 손익률, 비중 계산을 검증합니다.
 */
class KbAccountServiceTest {

    @Test
    @DisplayName("KB 보유 주식 응답으로 평가금액, 손익률, 비중을 계산한다")
    void holdingsCalculatesPortfolioSummaryAndWeights() throws Exception {
        KbSecuritiesAccountClient client = new FixtureKbClient(json("""
            {
              "dataBody": {
                "Record1": [
                  {
                    "is_no": "005930",
                    "is_nm": "삼성전자",
                    "gnrl_q": "10",
                    "averageBuyPrice": "70000",
                    "currentPrice": "77000"
                  },
                  {
                    "is_no": "000660",
                    "is_nm": "SK하이닉스",
                    "gnrl_q": "2",
                    "averageBuyPrice": "200000",
                    "currentPrice": "180000"
                  }
                ]
              }
            }
            """));
        KbAccountService service = new KbAccountService(client);

        KbHoldingsResponse response = service.holdings();

        assertThat(response.summary().totalPurchaseAmount()).isEqualByComparingTo("1100000");
        assertThat(response.summary().totalValuationAmount()).isEqualByComparingTo("1130000");
        assertThat(response.summary().totalProfitAmount()).isEqualByComparingTo("30000");
        assertThat(response.summary().profitRate()).isEqualByComparingTo("2.73");
        assertThat(response.items()).hasSize(2);
        assertThat(response.items().get(0).stockCode()).isEqualTo("005930");
        assertThat(response.items().get(0).stockName()).isEqualTo("삼성전자");
        assertThat(response.items().get(0).profitRate()).isEqualByComparingTo("10");
        assertThat(response.items().get(0).weightRate()).isEqualByComparingTo("68.14");
        assertThat(response.items().get(1).weightRate()).isEqualByComparingTo("31.86");
    }

    @Test
    @DisplayName("결제기준 잔고 현황 응답을 요약과 종목별 상세로 변환한다")
    void settlementBalanceMapsSummaryAndItems() throws Exception {
        KbAccountService service = new KbAccountService(new FixtureKbClient(null, json("""
            {
              "dataBody": {
                "tfnd": "100000",
                "o_amt_psbl_amt": "90000",
                "ordr_psbl_csh": "80000",
                "byng_amt_sum": "1100000",
                "pl_amt_sum": "30000",
                "val_amt_sum": "1130000",
                "yld_sum": "2.73",
                "tl_data_cnt": "1",
                "Record1": [
                  {
                    "gds_typ": "주식",
                    "clsf": "현금",
                    "crncy_cd": "KRW",
                    "is_cd": "005930",
                    "is_nm": "삼성전자",
                    "blnc_q": "10",
                    "ordr_psbl_q": "8",
                    "now_prc": "77000",
                    "byng_avr_prc": "70000",
                    "pl_amt": "70000",
                    "val_amt": "770000",
                    "yld": "10",
                    "val_sgrvt_p2": "68.14",
                    "fnl_ccls_excg_cd": "KRX"
                  }
                ]
              }
            }
            """)));

        KbBalanceResponse response = service.settlementBalance();

        assertThat(response.summary().basis()).isEqualTo("SETTLEMENT");
        assertThat(response.summary().totalValuationAmount()).isEqualByComparingTo("1130000");
        assertThat(response.summary().totalProfitAmount()).isEqualByComparingTo("30000");
        assertThat(response.summary().totalYieldRate()).isEqualByComparingTo("2.73");
        assertThat(response.items()).hasSize(1);
        assertThat(response.items().get(0).stockCode()).isEqualTo("005930");
        assertThat(response.items().get(0).quantity()).isEqualByComparingTo("10");
        assertThat(response.items().get(0).valuationWeightRate()).isEqualByComparingTo("68.14");
    }

    @Test
    @DisplayName("보유 주식 응답에 종목 배열이 없으면 가짜 알 수 없는 종목을 만들지 않는다")
    void holdingsDoesNotCreateUnknownItemWhenRecordArrayIsMissing() throws Exception {
        KbAccountService service = new KbAccountService(new FixtureKbClient(json("""
            {
              "dataBody": {
                "tl_data_cnt": "0",
                "nxt_key": ""
              }
            }
            """)));

        KbHoldingsResponse response = service.holdings();

        assertThat(response.items()).isEmpty();
        assertThat(response.summary().totalValuationAmount()).isEqualByComparingTo("0");
    }

    @Test
    @DisplayName("잔고 현황 응답에 종목 배열이 없으면 가짜 알 수 없는 종목을 만들지 않는다")
    void balanceDoesNotCreateUnknownItemWhenRecordArrayIsMissing() throws Exception {
        KbAccountService service = new KbAccountService(new FixtureKbClient(null, json("""
            {
              "dataBody": {
                "tfnd": "0",
                "val_amt_sum": "0",
                "tl_data_cnt": "0"
              }
            }
            """)));

        KbBalanceResponse response = service.settlementBalance();

        assertThat(response.items()).isEmpty();
        assertThat(response.summary().totalValuationAmount()).isEqualByComparingTo("0");
    }

    @Test
    @DisplayName("체결기준 잔고 현황 응답을 요약과 종목별 상세로 변환한다")
    void executionBalanceMapsSummaryAndItems() throws Exception {
        KbAccountService service = new KbAccountService(new FixtureKbClient(null, null, json("""
            {
              "dataBody": {
                "nt_asts_val_amt": "1500000",
                "val_amt_sum": "1130000",
                "val_pl_sum": "30000",
                "byng_amt_sum": "1100000",
                "val_yld_sum": "2.73",
                "tl_data_cnt": "1",
                "Record1": [
                  {
                    "clsf": "현금",
                    "crncy_cd": "KRW",
                    "is_cd": "005930",
                    "is_nm": "삼성전자",
                    "hld_q": "10",
                    "ordr_psbl_q": "8",
                    "nstmt_s_q": "1",
                    "nstmt_b_q": "2",
                    "ec_q": "9",
                    "byng_amt": "700000",
                    "now_prc": "77000",
                    "byng_avr_prc": "70000",
                    "val_amt": "770000",
                    "val_pl": "70000",
                    "val_yld": "10",
                    "fnl_ccls_excg_cd": "KRX"
                  }
                ]
              }
            }
            """)));

        KbBalanceResponse response = service.executionBalance();

        assertThat(response.summary().basis()).isEqualTo("EXECUTION");
        assertThat(response.summary().netAssetValuationAmount()).isEqualByComparingTo("1500000");
        assertThat(response.items()).hasSize(1);
        assertThat(response.items().get(0).stockCode()).isEqualTo("005930");
        assertThat(response.items().get(0).unsettledSellQuantity()).isEqualByComparingTo("1");
        assertThat(response.items().get(0).settlementQuantity()).isEqualByComparingTo("9");
    }

    @Test
    @DisplayName("계좌 목록 경로가 없으면 설정 계좌를 마스킹해서 반환한다")
    void accountsReturnsMaskedConfiguredAccountWhenPathIsMissing() {
        KbAccountService service = new KbAccountService(new FixtureKbClient(null));

        assertThat(service.accounts().items()).hasSize(1);
        assertThat(service.accounts().items().get(0).maskedAccountNumber()).isEqualTo("****7890");
    }

    @Test
    @DisplayName("계좌 목록 경로와 설정 계좌가 모두 없으면 빈 계좌 목록을 반환한다")
    void accountsReturnsEmptyItemsWhenPathAndConfiguredAccountAreMissing() {
        KbAccountService service = new KbAccountService(new FixtureKbClient(null, false));

        assertThat(service.accounts().items()).isEmpty();
    }

    private static JsonNode json(String value) throws Exception {
        return new ObjectMapper().readTree(value);
    }

    private static class FixtureKbClient extends KbSecuritiesAccountClient {
        private final JsonNode holdingsResponse;
        private final JsonNode settlementBalanceResponse;
        private final JsonNode executionBalanceResponse;

        FixtureKbClient(JsonNode holdingsResponse) {
            this(holdingsResponse, true);
        }

        FixtureKbClient(JsonNode holdingsResponse, JsonNode settlementBalanceResponse) {
            this(holdingsResponse, settlementBalanceResponse, null, true);
        }

        FixtureKbClient(JsonNode holdingsResponse, JsonNode settlementBalanceResponse, JsonNode executionBalanceResponse) {
            this(holdingsResponse, settlementBalanceResponse, executionBalanceResponse, true);
        }

        FixtureKbClient(JsonNode holdingsResponse, boolean hasAccountNumber) {
            this(holdingsResponse, null, null, hasAccountNumber);
        }

        FixtureKbClient(
            JsonNode holdingsResponse,
            JsonNode settlementBalanceResponse,
            JsonNode executionBalanceResponse,
            boolean hasAccountNumber
        ) {
            super(properties(hasAccountNumber), RestClient.builder().build());
            this.holdingsResponse = holdingsResponse;
            this.settlementBalanceResponse = settlementBalanceResponse;
            this.executionBalanceResponse = executionBalanceResponse;
        }

        @Override
        public JsonNode fetchHoldings() {
            return holdingsResponse;
        }

        @Override
        public JsonNode fetchSettlementBalance() {
            return settlementBalanceResponse;
        }

        @Override
        public JsonNode fetchExecutionBalance() {
            return executionBalanceResponse;
        }

        private static SecuritiesProviderProperties properties(boolean hasAccountNumber) {
            SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
            Provider kb = new Provider();
            kb.setAccountEnabled(true);
            if (hasAccountNumber) {
                kb.setAccountNumber("1234567890");
                kb.setAccountProductCode("01");
            }
            properties.setKb(kb);
            return properties;
        }
    }
}
