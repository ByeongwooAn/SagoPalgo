package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Completeness;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Section;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class KbAccountSnapshotServiceTest {
    private final ObjectMapper mapper = new ObjectMapper().findAndRegisterModules();
    private final SecuritiesProviderProperties properties = new SecuritiesProviderProperties();
    private final KbSecuritiesAccountClient client = mock(KbSecuritiesAccountClient.class);
    private final Clock clock = Clock.fixed(Instant.parse("2026-11-01T15:30:00Z"), ZoneOffset.UTC);
    private KbAccountSnapshotService service;

    @BeforeEach
    void setup() throws Exception {
        var kb = properties.getKb();
        kb.setAccountEnabled(true);
        kb.setHoldingsPath("/api/v1/ssqm1801");
        kb.setSettlementBalancePath("/api/v1/ssqm2932");
        kb.setExecutionBalancePath("/api/v1/ssqm2952");
        service = new KbAccountSnapshotService(client, properties, clock);
        when(client.fetchHoldingsPage(anyString())).thenReturn(ok("""
            {"Record1":[],"grid_cnt1":"0","nxt_key":""}
            """));
        when(client.fetchSettlementBalance()).thenReturn(ok("""
            {"Record1":[],"tl_data_cnt":"0","ordr_psbl_csh":"0"}
            """));
        when(client.fetchExecutionBalance()).thenReturn(ok("""
            {"Record1":[],"tl_data_cnt":"0","nt_asts_val_amt":"0"}
            """));
        when(client.fetchOrderExecutions(anyString(), eq("0"), anyString())).thenReturn(ok("""
            {"ordr_dt":"20261102","Record1":[],"nxt_key":""}
            """));
    }

    @Test
    void completeEmptyResultHasExplicitScopeAndNeverAuthorizesTrading() {
        var result = service.observe(null);
        assertThat(result.status()).isEqualTo(Status.SUCCESS);
        assertThat(result.atomic()).isFalse();
        assertThat(result.usableForTrading()).isFalse();
        assertThat(result.startedAt()).isEqualTo(clock.instant());
        assertThat(result.sections()).hasSize(4).allSatisfy(section -> {
            assertThat(section.rows()).isEmpty();
            assertThat(section.completeness()).isEqualTo(Completeness.COMPLETE);
            assertThat(section.providerProcessTime()).isEqualTo("20261102003000000");
        });
        assertThat(result.sections().get(3).scope()).containsEntry("orderDate", "20261102");
        verify(client).fetchHoldingsPage("");
        verify(client).fetchSettlementBalance();
        verify(client).fetchExecutionBalance();
        verify(client).fetchOrderExecutions("20261102", "0", "");
        verifyNoMoreInteractions(client);
    }

    @Test
    void preservesSixDecimalStringsAndNullsWithoutDerivingOrRounding() throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(ok("""
            {"tl_data_cnt":"1","Record1":[{"is_cd":"005930","crncy_cd":"KRW",
              "hld_q":"0","hld_q_p6":"0.123456","ordr_psbl_q_p6":"0.000001",
              "byng_amt":"1,234.560000","val_pl":"-0.000001"}],"access_token":"do-not-copy"}
            """));
        var section = execution();
        assertThat(section.rows().get(0).fields())
            .containsEntry("hld_q_p6", "0.123456")
            .containsEntry("ordr_psbl_q_p6", "0.000001")
            .containsEntry("byng_amt", "1234.560000")
            .containsEntry("val_pl", "-0.000001")
            .containsEntry("now_prc", null);
        mapper.setSerializationInclusion(JsonInclude.Include.NON_NULL);
        JsonNode json = mapper.readTree(mapper.writeValueAsString(section));
        assertThat(json.path("rows").get(0).path("fields").has("now_prc")).isTrue();
        assertThat(json.path("rows").get(0).path("fields").get("now_prc").isNull()).isTrue();
        assertThat(json.toString()).doesNotContain("do-not-copy", "access_token");
    }

    @Test
    void followsHoldingsAndOrdersCursorsExactlyAndKeepsRequestWindow() throws Exception {
        when(client.fetchHoldingsPage("")).thenReturn(ok("""
            {"Record1":[{"is_no":"005930","gnrl_q":"1"}],"nxt_key":"hold-key  "}
            """));
        when(client.fetchHoldingsPage("hold-key  ")).thenReturn(ok("""
            {"Record1":[{"is_no":"000660","gnrl_q":"2"}],"nxt_key":""}
            """));
        when(client.fetchOrderExecutions("20261102", "0", "")).thenReturn(ok("""
            {"ordr_dt":"20261102","Record1":[{"ordr_no":"0000000011","ordr_q":"5"}],"nxt_key":"order-key  "}
            """));
        when(client.fetchOrderExecutions("20261102", "0", "order-key  ")).thenReturn(ok("""
            {"ordr_dt":"20261102","Record1":[{"ordr_no":"0000000012","nccls_q":"2"}],"nxt_key":""}
            """));
        var snapshot = service.observe("20261102");
        assertThat(snapshot.status()).isEqualTo(Status.SUCCESS);
        assertThat(snapshot.sections().get(0).pagesRead()).isEqualTo(2);
        assertThat(snapshot.sections().get(0).rows()).hasSize(2);
        assertThat(snapshot.sections().get(3).pagesRead()).isEqualTo(2);
        assertThat(snapshot.sections().get(3).rows()).hasSize(2);
    }

    @Test
    void missingArrayWithoutExplicitZeroIsNotAnEmptySuccess() throws Exception {
        when(client.fetchHoldingsPage("")).thenReturn(ok("{\"nxt_key\":\"\"}"));
        var section = holdings();
        assertThat(section.status()).isEqualTo(Status.PARTIAL);
        assertThat(section.completeness()).isEqualTo(Completeness.UNKNOWN);
        assertThat(section.issues()).extracting("code").contains("MISSING_RECORDS");
    }

    @Test
    void explicitZeroCountAllowsOmittedEmptyArray() throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(ok("{\"tl_data_cnt\":\"0000\"}"));
        assertThat(execution().completeness()).isEqualTo(Completeness.COMPLETE);
    }

    @Test
    void countLargerThanRowsShowsTruncationAndMissingCountRemainsUnknown() throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(ok("{\"tl_data_cnt\":\"2\",\"Record1\":[]}"));
        assertThat(execution().completeness()).isEqualTo(Completeness.PARTIAL);
        when(client.fetchExecutionBalance()).thenReturn(ok("{\"Record1\":[]}"));
        assertThat(execution().completeness()).isEqualTo(Completeness.UNKNOWN);
    }

    @Test
    void countMismatchAndPlaceholderRowsCannotClaimComplete() throws Exception {
        when(client.fetchHoldingsPage("")).thenReturn(ok("""
            {"grid_cnt1":"1","Record1":[],"nxt_key":""}
            """));
        assertThat(holdings().completeness()).isEqualTo(Completeness.INVALID);
        when(client.fetchExecutionBalance()).thenReturn(ok("{\"tl_data_cnt\":\"1\",\"Record1\":[{}]}"));
        assertThat(execution().completeness()).isEqualTo(Completeness.INVALID);
    }

    @Test
    void missingNextKeyIsNotInferredAsEndOfPages() throws Exception {
        when(client.fetchHoldingsPage("")).thenReturn(ok("{\"Record1\":[]}"));
        assertThat(holdings().completeness()).isEqualTo(Completeness.UNKNOWN);
    }

    @Test
    void repeatedCursorStopsWithoutRetryingAndKeepsObservedRows() throws Exception {
        when(client.fetchHoldingsPage(anyString())).thenReturn(ok("""
            {"Record1":[{"is_no":"005930","gnrl_q":"1"}],"nxt_key":"same"}
            """));
        var result = holdings();
        assertThat(result.pagesRead()).isEqualTo(2);
        assertThat(result.rows()).hasSize(2);
        assertThat(result.completeness()).isEqualTo(Completeness.PARTIAL);
        assertThat(result.issues()).extracting("code").contains("REPEATED_NEXT_KEY", "DUPLICATE_IDENTITY");
        verify(client, times(1)).fetchHoldingsPage("same");
    }

    @Test
    void pageLimitStopsUnboundedScan() throws Exception {
        AtomicInteger pages = new AtomicInteger();
        when(client.fetchHoldingsPage(anyString())).thenAnswer(call -> ok(
            "{\"Record1\":[],\"nxt_key\":\"p" + pages.incrementAndGet() + "\"}"));
        var section = holdings();
        assertThat(section.pagesRead()).isEqualTo(10);
        assertThat(section.issues()).extracting("code").contains("PAGE_LIMIT");
        verify(client, times(10)).fetchHoldingsPage(anyString());
    }

    @Test
    void partialPageFailureIsIsolatedAndNeverLeaksExceptionText() throws Exception {
        when(client.fetchHoldingsPage("")).thenReturn(ok("""
            {"Record1":[{"is_no":"005930","gnrl_q":"1"}],"nxt_key":"second"}
            """));
        when(client.fetchHoldingsPage("second")).thenThrow(new IllegalStateException("secret-token account-number"));
        var result = service.observe(null);
        assertThat(result.status()).isEqualTo(Status.PARTIAL);
        assertThat(result.sections().get(0).rows()).hasSize(1);
        assertThat(result.sections().get(0).completeness()).isEqualTo(Completeness.PARTIAL);
        assertThat(result.sections().get(1).status()).isEqualTo(Status.SUCCESS);
        assertThat(mapper.writeValueAsString(result)).doesNotContain("secret-token", "account-number");
        verify(client).fetchHoldingsPage("second");
    }

    @Test
    void disabledAccountDoesNotCallEvenReadOrTokenPaths() {
        properties.getKb().setAccountEnabled(false);
        assertThat(service.observe(null).status()).isEqualTo(Status.DISABLED);
        verifyNoInteractions(client);
    }

    @Test
    void configurationChangeDiscardsAllMixedAccountData() throws Exception {
        when(client.fetchSettlementBalance()).thenAnswer(call -> {
            properties.getKb().setAppKey("changed-key");
            return ok("{\"tl_data_cnt\":\"0\",\"Record1\":[]}");
        });
        var result = service.observe(null);
        assertThat(result.status()).isEqualTo(Status.FAILED);
        assertThat(result.sections()).allSatisfy(section -> {
            assertThat(section.rows()).isEmpty();
            assertThat(section.summary()).isEmpty();
            assertThat(section.issues()).extracting("code").containsExactly("CONTEXT_CHANGED");
        });
        verify(client, never()).fetchExecutionBalance();
        verify(client, never()).fetchOrderExecutions(anyString(), anyString(), anyString());
    }

    @Test
    void unsupportedConfiguredPathIsNotMislabelledAsOfficialContract() {
        properties.getKb().setHoldingsPath("/custom/holdings");
        assertThat(holdings().issues()).extracting("code").contains("UNSUPPORTED_CONTRACT");
        verify(client, never()).fetchHoldingsPage(anyString());
    }

    @ParameterizedTest
    @ValueSource(strings = {"20260230", "2026-11-02", "20261102 ", "", "00000000"})
    void invalidOrderDateFailsBeforeAnyIo(String date) {
        assertThatThrownBy(() -> service.observe(date)).isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);
        verifyNoInteractions(client);
    }

    @ParameterizedTest
    @ValueSource(strings = {"1,,2", "1e-6", "NaN", "-0.000001"})
    void malformedOrNegativeQuantityIsUnknownInsteadOfZero(String value) throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(ok("{\"tl_data_cnt\":\"1\",\"Record1\":[{"
            + "\"is_cd\":\"005930\",\"hld_q_p6\":\"" + value + "\"}]}"));
        var result = execution();
        assertThat(result.rows().get(0).fields()).containsEntry("hld_q_p6", null);
        assertThat(result.completeness()).isEqualTo(Completeness.INVALID);
    }

    @Test
    void floatingJsonNumberIsRejectedInsteadOfLosingDecimalPrecision() throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(ok("""
            {"tl_data_cnt":"1","Record1":[{"is_cd":"005930","hld_q_p6":0.123456}]}
            """));
        assertThat(execution().issues()).extracting("code").contains("INVALID_NUMBER");
    }

    @Test
    void wrongDateDoesNotMixOrderDays() throws Exception {
        when(client.fetchOrderExecutions(anyString(), eq("0"), anyString())).thenReturn(ok("""
            {"ordr_dt":"20261101","Record1":[{"ordr_no":"0000000001"}],"nxt_key":""}
            """));
        var orders = service.observe(null).sections().get(3);
        assertThat(orders.rows()).isEmpty();
        assertThat(orders.completeness()).isEqualTo(Completeness.INVALID);
    }

    @Test
    void repeatedRequestAndNewServiceNeverReturnAnOldCachedSnapshot() throws Exception {
        var first = service.observe(null);
        when(client.fetchExecutionBalance()).thenReturn(ok("""
            {"tl_data_cnt":"1","Record1":[{"is_cd":"005930","hld_q_p6":"0.000001"}]}
            """));
        var second = service.observe(null);
        var restarted = new KbAccountSnapshotService(client, properties, clock).observe(null);
        assertThat(first.sections().get(2).rows()).isEmpty();
        assertThat(second.sections().get(2).rows()).hasSize(1);
        assertThat(restarted.sections().get(2).rows()).isEqualTo(second.sections().get(2).rows());
        assertThat(first.observationId()).isNotEqualTo(second.observationId());
        assertThat(second.observationId()).isNotEqualTo(restarted.observationId());
        verify(client, times(3)).fetchExecutionBalance();
    }

    @Test
    void rowLimitAlsoBoundsMalformedRowsAndPreservesTruncation() throws Exception {
        var response = ok("{\"tl_data_cnt\":\"501\",\"Record1\":[]}");
        var records = (com.fasterxml.jackson.databind.node.ArrayNode) response.path("dataBody").path("Record1");
        for (int i = 0; i < 501; i++) records.addNull();
        when(client.fetchExecutionBalance()).thenReturn(response);
        var result = execution();
        assertThat(result.receivedRowCount()).isEqualTo(501);
        assertThat(result.rows()).isEmpty();
        assertThat(result.completeness()).isEqualTo(Completeness.PARTIAL);
        assertThat(result.issues().stream().filter(i -> i.code().equals("INVALID_ROW"))).hasSize(500);
        assertThat(result.issues()).extracting("code").contains("ROW_LIMIT");
    }

    @Test
    void noSuccessfulBrokerReadProducesFailedSnapshotWithoutOldData() {
        when(client.fetchHoldingsPage(anyString())).thenThrow(new IllegalStateException("private"));
        when(client.fetchSettlementBalance()).thenThrow(new IllegalStateException("private"));
        when(client.fetchExecutionBalance()).thenThrow(new IllegalStateException("private"));
        when(client.fetchOrderExecutions(anyString(), anyString(), anyString())).thenThrow(new IllegalStateException("private"));
        var result = service.observe(null);
        assertThat(result.status()).isEqualTo(Status.FAILED);
        assertThat(result.sections()).allSatisfy(s -> {
            assertThat(s.pagesRead()).isZero();
            assertThat(s.rows()).isEmpty();
        });
    }

    @ParameterizedTest
    @ValueSource(strings = {
        "{\"dataBody\":{\"Record1\":[],\"tl_data_cnt\":\"0\"}}",
        "{\"dataHeader\":{\"resultCode\":\"200\",\"processFlag\":\"B\"},\"dataBody\":{\"Record1\":[],\"tl_data_cnt\":\"0\"}}",
        "{\"dataHeader\":{\"resultCode\":\"200\",\"processFlag\":\"A\"},\"dataBody\":[]}"
    })
    void invalidEnvelopeNeverCreatesAnEmptySuccess(String json) throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(mapper.readTree(json));
        assertThat(execution().status()).isEqualTo(Status.FAILED);
    }

    @Test
    void noProviderTimestampDoesNotInventAnAsOfTime() throws Exception {
        when(client.fetchExecutionBalance()).thenReturn(mapper.readTree("""
            {"dataHeader":{"resultCode":"200","processFlag":"A"},"dataBody":{"Record1":[],"tl_data_cnt":"0"}}
            """));
        var section = execution();
        assertThat(section.providerProcessTime()).isNull();
        assertThat(section.startedAt()).isEqualTo(clock.instant());
        assertThat(section.status()).isEqualTo(Status.SUCCESS);
    }

    @Test
    void controlOnlyCursorCannotBeTreatedAsTerminalWhitespace() throws Exception {
        var response = ok("{\"Record1\":[],\"nxt_key\":\"\"}");
        ((com.fasterxml.jackson.databind.node.ObjectNode) response.path("dataBody")).put("nxt_key", "\n");
        when(client.fetchHoldingsPage("")).thenReturn(response);
        var section = holdings();
        assertThat(section.completeness()).isEqualTo(Completeness.PARTIAL);
        assertThat(section.issues()).extracting("code").contains("INVALID_NEXT_KEY");
    }

    private Section holdings() { return service.observe(null).sections().get(0); }
    private Section execution() { return service.observe(null).sections().get(2); }

    private JsonNode ok(String body) throws Exception {
        return mapper.readTree("{\"dataHeader\":{\"resultCode\":\"200\",\"processFlag\":\"A\","
            + "\"processTime\":\"20261102003000000\"},\"dataBody\":" + body + "}");
    }
}
