package com.sagopalgo.api.order.client;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import java.math.BigDecimal;
import java.util.Map;
import org.junit.jupiter.api.Test;

class KbLimitOrderContractTest {
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void encodesOfficialRegularSessionLimitOrderFields() {
        var buy = KbLimitOrderContract.encode(request("BUY", "005930", "360000", "5"));
        var sell = KbLimitOrderContract.encode(request("SELL", "005930", "320000", "1"));

        assertThat(buy.path()).isEqualTo("/api/v1/ssam1802");
        assertThat(sell.path()).isEqualTo("/api/v1/ssam1801");
        assertThat(buy.dataBody()).containsExactlyInAnyOrderEntriesOf(Map.of(
            "mkt_tm_clsf", "1",
            "is_cd", "005930",
            "ordr_q", "5",
            "ordr_uprc", "360000",
            "ordr_ccd", "00",
            "sor_ordr_ccd", "K"
        ));
    }

    @Test
    void rejectsFractionalOrOversizedFieldsBeforeEncoding() {
        assertThatThrownBy(() -> KbLimitOrderContract.encode(request("BUY", "005930", "100.5", "1")))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> KbLimitOrderContract.encode(request("BUY", "005930", "100", "1.5")))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> KbLimitOrderContract.encode(request("BUY", "005930", "1000000000", "1")))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> KbLimitOrderContract.encode(request("BUY", "005930", "100", "10000000000")))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> KbLimitOrderContract.encode(request("BUY", "A005930", "100", "1")))
            .isInstanceOf(ApiException.class);
    }
    @Test void selectedQuantityEncodesPartialAndFullScopeWithoutChangingExistingLiveContract() {
        var plan=request("BUY","005930","76000","2");
        assertThat(KbLimitOrderContract.encodeChange(plan,"AMEND","0040000638",new BigDecimal("5")).dataBody())
            .containsEntry("crct_clsf","1").containsEntry("ordr_q","2").containsEntry("ordr_uprc","76000");
        assertThat(KbLimitOrderContract.encodeChange(plan,"CANCEL","0040000638",new BigDecimal("5")).dataBody())
            .containsEntry("crct_clsf","1").containsEntry("ordr_q","2").doesNotContainKey("ordr_uprc");
        assertThat(KbLimitOrderContract.encodeChange(plan,"AMEND","0040000638").dataBody()).containsEntry("crct_clsf","2");
        assertThatThrownBy(()->KbLimitOrderContract.encodeChange(plan,"AMEND","0040000638",BigDecimal.ONE)).isInstanceOf(ApiException.class);
    }

    @Test
    void acceptsOnlyExplicitSuccessWithRealOrderNumber() throws Exception {
        var response = objectMapper.readTree("""
            {
              "dataHeader": {"resultCode":"200","processFlag":"A","processCode":"0005"},
              "dataBody": {"ordr_no":"0040000638","o_msg":"정상적으로 매수주문 완료되었습니다."}
            }
            """);

        var outcome = KbLimitOrderContract.interpret(response);

        assertThat(outcome.status()).isEqualTo(KbLimitOrderContract.Status.ACCEPTED);
        assertThat(outcome.orderNumber()).isEqualTo("0040000638");
    }

    @Test
    void rejectsBrokerFailureEvenWhenHttpLevelResultCodeIs200() throws Exception {
        var response = objectMapper.readTree("""
            {
              "dataHeader": {"resultCode":"200","processFlag":"B","processCode":"1853"},
              "dataBody": {"ordr_no":"0000000000","o_msg":"제권리 수량이 없습니다."}
            }
            """);

        var outcome = KbLimitOrderContract.interpret(response);

        assertThat(outcome.status()).isEqualTo(KbLimitOrderContract.Status.REJECTED);
        assertThat(outcome.orderNumber()).isEmpty();
        assertThat(outcome.message()).contains("수량");
    }

    @Test
    void treatsIncompleteOrConflictingResponseAsUnknownNotRetryableSuccess() throws Exception {
        var incomplete = objectMapper.readTree("""
            {"dataHeader":{"resultCode":"200","processFlag":"A"},"dataBody":{"ordr_no":"0000000000"}}
            """);
        var conflicting = objectMapper.readTree("""
            {"dataHeader":{"resultCode":"500","processFlag":"A"},"dataBody":{"ordr_no":"0040000638"}}
            """);
        var rejectedWithOrderNumber = objectMapper.readTree("""
            {"dataHeader":{"resultCode":"200","processFlag":"B"},"dataBody":{"ordr_no":"0040000638"}}
            """);

        assertThat(KbLimitOrderContract.interpret(incomplete).status())
            .isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
        assertThat(KbLimitOrderContract.interpret(conflicting).status())
            .isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
        assertThat(KbLimitOrderContract.interpret(rejectedWithOrderNumber).status())
            .isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
        assertThat(KbLimitOrderContract.interpret(null).status())
            .isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
    }

    @Test
    void malformedOrderNumberOrConflictingFailureNeverBecomesAcceptedOrRejected() throws Exception {
        for (String number : java.util.List.of("123", "ABCDEFGHIJ", "00400006381")) {
            var response=objectMapper.readTree("{\"dataHeader\":{\"resultCode\":\"200\",\"processFlag\":\"A\"},\"dataBody\":{\"ordr_no\":\""+number+"\"}}");
            assertThat(KbLimitOrderContract.interpret(response).status()).isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
        }
        var conflicting=objectMapper.readTree("{\"dataHeader\":{\"resultCode\":\"500\",\"processFlag\":\"B\"},\"dataBody\":{}}");
        assertThat(KbLimitOrderContract.interpret(conflicting).status()).isEqualTo(KbLimitOrderContract.Status.UNKNOWN);
    }

    private OrderPrecheckRequest request(String side, String stockCode, String price, String quantity) {
        return new OrderPrecheckRequest(
            stockCode, "삼성전자", "KOSPI", side, new BigDecimal(price), new BigDecimal(quantity)
        );
    }
}
