package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class KbOrderExecutionServiceTest {
    @Mock private KbSecuritiesAccountClient kbClient;

    private KbOrderExecutionService service;
    private final ObjectMapper objectMapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        service = new KbOrderExecutionService(kbClient);
    }

    @Test
    void mapsOpenPartialFilledAndUncertainRecordsWithoutInventingCancellation() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(response("CURSOR  ", """
                {"ordr_no":"0040000001","stnd_is_no":"005930","hngl_shrt_nm":"삼성전자",
                 "trd_dl_ccd_nm":"매수","ordr_tm":"101500","ordr_q":"0000000010",
                 "tl_ccls_q":"0000000000","nccls_q":"0000000010","ordr_uprc":"000075000"},
                {"ordr_no":"0040000002","ordr_q":"10","tl_ccls_q":"4","nccls_q":"6"},
                {"ordr_no":"0040000003","ordr_q":"10","tl_ccls_q":"10","nccls_q":"0"},
                {"ordr_no":"0040000004","ordr_q":"10","tl_ccls_q":"4","nccls_q":"0"}
                """));

        var page = service.page("20260923", "0", null);

        assertThat(page.nextKey()).isEqualTo("CURSOR  ");
        assertThat(page.items()).extracting("status").containsExactly("OPEN", "PARTIAL", "FILLED", "UNKNOWN");
        assertThat(page.items().get(0).orderQuantity()).isEqualByComparingTo("10");
        assertThat(page.items().get(0).orderPrice()).isEqualByComparingTo("75000");
        assertThat(page.items().get(0).stockName()).isEqualTo("삼성전자");
    }

    @Test
    void scansSubsequentPagesForOrderNumberAndReportsCompleteScan() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(response("NEXT", """
                {"ordr_no":"0040000001","ordr_q":"1","tl_ccls_q":"0","nccls_q":"1"}
                """));
        when(kbClient.fetchOrderExecutions("20260923", "0", "NEXT"))
            .thenReturn(response("", """
                {"ordr_no":"0040000002","ordr_q":"2","tl_ccls_q":"2","nccls_q":"0"}
                """));

        var lookup = service.findByOrderNumber("20260923", "0040000002");

        assertThat(lookup.completeScan()).isTrue();
        assertThat(lookup.pagesScanned()).isEqualTo(2);
        assertThat(lookup.matches()).hasSize(1);
        assertThat(lookup.matches().get(0).status()).isEqualTo("FILLED");
    }

    @Test
    void repeatedContinuationKeyCannotBeMistakenForCompleteReconciliation() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(response("NEXT", ""));
        when(kbClient.fetchOrderExecutions("20260923", "0", "NEXT"))
            .thenReturn(response("NEXT", ""));

        var lookup = service.findByOrderNumber("20260923", "0040000002");

        assertThat(lookup.completeScan()).isFalse();
        assertThat(lookup.pagesScanned()).isEqualTo(2);
        assertThat(lookup.matches()).isEmpty();
    }

    @Test
    void nonblankContinuationFlagWithoutCursorRemainsIncomplete() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(objectMapper.readTree("""
                {"dataBody":{"cn_clsf":"Y","nxt_key":"","Record1":[]}}
                """));

        var lookup = service.findByOrderNumber("20260923", "0040000002");

        assertThat(lookup.completeScan()).isFalse();
        assertThat(lookup.matches()).isEmpty();
    }

    @Test
    void scansWholeDateAcrossPagesWithoutInferringAnOrderMatch() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(response("NEXT", """
                {"ordr_no":"0040000001","ordr_q":"1","tl_ccls_q":"0","nccls_q":"1"}
                """));
        when(kbClient.fetchOrderExecutions("20260923", "0", "NEXT"))
            .thenReturn(response("", """
                {"ordr_no":"0040000002","ordr_q":"2","tl_ccls_q":"2","nccls_q":"0"}
                """));

        var scan = service.scanDate("20260923");

        assertThat(scan.completeScan()).isTrue();
        assertThat(scan.pagesScanned()).isEqualTo(2);
        assertThat(scan.itemLimitReached()).isFalse();
        assertThat(scan.items()).extracting("orderNo").containsExactly("0040000001", "0040000002");
    }

    @Test
    void repeatedDateCursorRemainsIncomplete() throws Exception {
        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(response("NEXT", ""));
        when(kbClient.fetchOrderExecutions("20260923", "0", "NEXT"))
            .thenReturn(response("NEXT", ""));

        var scan = service.scanDate("20260923");

        assertThat(scan.completeScan()).isFalse();
        assertThat(scan.pagesScanned()).isEqualTo(2);
    }

    @Test
    void dateScanItemCapNeverLooksComplete() {
        ObjectNode body = objectMapper.createObjectNode();
        body.put("nxt_key", "");
        ArrayNode records = body.putArray("Record1");
        for (int index = 1; index <= 201; index++) {
            ObjectNode record = records.addObject();
            record.put("ordr_no", "%010d".formatted(index));
            record.put("ordr_q", "1");
            record.put("tl_ccls_q", "0");
            record.put("nccls_q", "1");
        }
        ObjectNode response = objectMapper.createObjectNode();
        response.set("dataBody", body);
        when(kbClient.fetchOrderExecutions("20260923", "0", "")).thenReturn(response);

        var scan = service.scanDate("20260923");

        assertThat(scan.completeScan()).isFalse();
        assertThat(scan.itemLimitReached()).isTrue();
        assertThat(scan.items()).hasSize(200);
    }

    @Test
    void rejectsMalformedDatesAndMissingBrokerRecordArray() throws Exception {
        assertThatThrownBy(() -> service.page("20260230", "0", ""))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.page("20260923", "3", ""))
            .isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.findByOrderNumber("20260923", "0000000000"))
            .isInstanceOf(ApiException.class);
        verify(kbClient, never()).fetchOrderExecutions("20260230", "0", "");

        when(kbClient.fetchOrderExecutions("20260923", "0", ""))
            .thenReturn(objectMapper.readTree("""
                {"dataBody":{"nxt_key":""}}
                """));
        assertThatThrownBy(() -> service.page("20260923", "0", ""))
            .isInstanceOf(ApiException.class)
            .hasMessageContaining("Record1");
    }

    private JsonNode response(String nextKey, String records) throws Exception {
        return objectMapper.readTree("""
            {"dataBody":{"nxt_key":%s,"Record1":[%s]}}
            """.formatted(objectMapper.writeValueAsString(nextKey), records));
    }
}
