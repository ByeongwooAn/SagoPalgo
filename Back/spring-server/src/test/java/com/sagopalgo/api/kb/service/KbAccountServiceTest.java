package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
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
                "holdings": [
                  {
                    "stockCode": "005930",
                    "stockName": "삼성전자",
                    "quantity": "10",
                    "averageBuyPrice": "70000",
                    "currentPrice": "77000"
                  },
                  {
                    "stockCode": "000660",
                    "stockName": "SK하이닉스",
                    "quantity": "2",
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
        assertThat(response.items().get(0).profitRate()).isEqualByComparingTo("10");
        assertThat(response.items().get(0).weightRate()).isEqualByComparingTo("68.14");
        assertThat(response.items().get(1).weightRate()).isEqualByComparingTo("31.86");
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

        FixtureKbClient(JsonNode holdingsResponse) {
            this(holdingsResponse, true);
        }

        FixtureKbClient(JsonNode holdingsResponse, boolean hasAccountNumber) {
            super(properties(hasAccountNumber), RestClient.builder().build());
            this.holdingsResponse = holdingsResponse;
        }

        @Override
        public JsonNode fetchHoldings() {
            return holdingsResponse;
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
