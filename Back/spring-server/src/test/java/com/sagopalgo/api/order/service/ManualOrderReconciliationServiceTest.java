package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import java.math.BigDecimal;
import java.time.*;
import java.util.List;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DataAccessResourceFailureException;

class ManualOrderReconciliationServiceTest {
    ManualOrderMapper commands = mock(ManualOrderMapper.class);
    ManualOrderReconciliationMapper mapper = mock(ManualOrderReconciliationMapper.class);
    OrderAccountBinding binding = mock(OrderAccountBinding.class);
    KbOrderExecutionService executions = mock(KbOrderExecutionService.class);
    ManualOrderReconciliationStore store = mock(ManualOrderReconciliationStore.class);
    ManualOrderReconciliationService service = new ManualOrderReconciliationService(commands, mapper, binding, executions, store);

    @BeforeEach void setup() {
        when(commands.find("command", 1L)).thenReturn(command("NEW", "UNKNOWN"));
        when(binding.matches("fingerprint")).thenReturn(true);
        when(executions.findByOrderNumber("20261031", "0040000638")).thenReturn(lookup(true, row("valid")));
    }

    @Test void preparationStoresOnlyTokenHashAndNeverUnlocks() {
        var result = service.prepare(1L, "command", "0040000638");
        var stored = ArgumentCaptor.forClass(ManualOrderReconciliationPreparation.class);
        verify(mapper).prepare(stored.capture());
        assertThat(stored.getValue().tokenHash()).hasSize(64).isNotEqualTo(result.token());
        assertThat(Duration.between(stored.getValue().checkedAt(), stored.getValue().expiresAt()).getSeconds()).isEqualTo(90);
        assertThat(result.command().toString()).doesNotContain("fingerprint");
        verifyNoInteractions(store);
        verify(commands, never()).finish(any(), any(), any(), any(), any(), any(), any());
    }

    @Test void confirmationRequiresAcknowledgementAndFreshFilledEvidence() {
        var preparation = prepare();
        var result = service.confirm(1L, "command", preparation.token(), true, "전량 체결 대조 확정");
        verify(executions, times(2)).findByOrderNumber("20261031", "0040000638");
        verify(store).confirm(argThat(r -> r.commandId().equals("command") && r.filledQuantity().compareTo(BigDecimal.ONE) == 0),
            anyString(), any());
        assertThat(result.orderNo()).isEqualTo("0040000638");
        assertThat(result.toString()).doesNotContain("fingerprint");
        verify(commands, never()).finish(any(), any(), any(), any(), any(), any(), any());
    }

    @Test void decliningOrWrongConfirmationDoesNotReadBrokerOrConsumeToken() {
        assertThatThrownBy(() -> service.confirm(1L, "command", "token", false, "전량 체결 대조 확정")).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.confirm(1L, "command", "token", true, "실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(executions, store);
    }

    @ParameterizedTest
    @ValueSource(strings = {"SENDING", "ACCEPTED", "REJECTED", "PREPARED"})
    void onlyFinishedUnknownTransmissionCanBeResolved(String status) {
        when(commands.find("command", 1L)).thenReturn(command("NEW", status));
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        verifyNoInteractions(executions, store);
    }

    @ParameterizedTest
    @ValueSource(strings = {"AMEND", "CANCEL"})
    void changesCannotBeMistakenForNewOrder(String kind) {
        when(commands.find("command", 1L)).thenReturn(command(kind, "UNKNOWN"));
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        verifyNoInteractions(executions, store);
    }

    @ParameterizedTest
    @ValueSource(strings = {"stock", "side", "price", "quantity", "partial", "open", "rejected", "early", "late", "badTime", "orderNo"})
    void mismatchedOrNotFullyFilledEvidenceKeepsLock(String scenario) {
        when(executions.findByOrderNumber("20261031", "0040000638")).thenReturn(lookup(true, row(scenario)));
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        verify(mapper, never()).prepare(any()); verifyNoInteractions(store);
    }

    @Test void partialPageDuplicateRowsAndEmptyResultNeverUnlock() {
        for (var result : List.of(lookup(false, row("valid")), lookup(true, row("valid"), row("valid")), lookup(true))) {
            when(executions.findByOrderNumber("20261031", "0040000638")).thenReturn(result);
            assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        }
        verify(mapper, never()).prepare(any()); verifyNoInteractions(store);
    }

    @ParameterizedTest
    @ValueSource(strings = {"0", "0000000000", "ABCDEFGHIJ", "00400006381"})
    void malformedOrderNumberPreventsLookup(String orderNo) {
        assertThatThrownBy(() -> service.prepare(1L, "command", orderNo)).isInstanceOf(ApiException.class);
        verifyNoInteractions(executions, store);
    }

    @Test void staleOrReplacedTokenPreventsSecondLookup() {
        var prepared = prepare();
        assertThatThrownBy(() -> service.confirm(1L, "command", "other-token", true, "전량 체결 대조 확정")).isInstanceOf(ApiException.class);
        var saved = mapper.preparation("command", 1L);
        when(mapper.preparation("command", 1L)).thenReturn(new ManualOrderReconciliationPreparation("command", 1L,
            "fingerprint", saved.orderNo(), saved.tokenHash(), LocalDateTime.now().minusDays(1), saved.checkedAt()));
        assertThatThrownBy(() -> service.confirm(1L, "command", prepared.token(), true, "전량 체결 대조 확정")).isInstanceOf(ApiException.class);
        verify(executions, times(1)).findByOrderNumber(any(), any()); verifyNoInteractions(store);
    }

    @Test void changedEvidenceAtFinalConfirmationPreventsSave() {
        var prepared = prepare();
        when(executions.findByOrderNumber("20261031", "0040000638")).thenReturn(lookup(true, row("partial")));
        assertThatThrownBy(() -> service.confirm(1L, "command", prepared.token(), true, "전량 체결 대조 확정")).isInstanceOf(ApiException.class);
        verifyNoInteractions(store);
    }

    @Test void alreadyKnownBrokerOrderOrChangedAccountIsBlocked() {
        when(mapper.brokerOrderAlreadyRecorded(any())).thenReturn(1);
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        when(binding.matches(any())).thenReturn(false);
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        verify(executions, times(1)).findByOrderNumber(any(), any()); verifyNoInteractions(store);
    }

    @Test void missingStorageAndForeignCommandCannotQueryBroker() {
        when(commands.find("command", 1L)).thenReturn(null);
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class);
        when(commands.verifyStorage()).thenThrow(new DataAccessResourceFailureException("private-db"));
        assertThatThrownBy(() -> service.prepare(1L, "command", "0040000638")).isInstanceOf(ApiException.class).hasMessageNotContaining("private-db");
        verifyNoInteractions(executions, store);
    }

    private ManualOrderReconciliationService.Preparation prepare() {
        var result = service.prepare(1L, "command", "0040000638");
        var captor = ArgumentCaptor.forClass(ManualOrderReconciliationPreparation.class);
        verify(mapper).prepare(captor.capture());
        when(mapper.preparation("command", 1L)).thenReturn(captor.getValue());
        return result;
    }

    private ManualOrderCommand command(String kind, String status) {
        var time = LocalDateTime.of(2026, 10, 31, 9, 0);
        return new ManualOrderCommand("command", 1L, 7L, null, kind, "005930", "삼성전자", "KOSPI", "BUY",
            new BigDecimal("100"), BigDecimal.ONE, "fingerprint", null, time.plusSeconds(90), status,
            null, "20261031", null, null, null, time, time);
    }

    private KbOrderLookupResponse lookup(boolean complete, KbOrderExecutionItemResponse... rows) {
        return new KbOrderLookupResponse("20261031", "0040000638", complete, 1, List.of(rows));
    }

    private KbOrderExecutionItemResponse row(String scenario) {
        String time = switch (scenario) {case "early" -> "085900"; case "late" -> "091000"; case "badTime" -> "250000"; default -> "090001";};
        return new KbOrderExecutionItemResponse(scenario.equals("orderNo") ? "0040000639" : "0040000638",
            scenario.equals("stock") ? "000660" : "005930", "삼성전자", scenario.equals("side") ? "매도" : "매수", time,
            scenario.equals("quantity") ? BigDecimal.TEN : BigDecimal.ONE,
            scenario.equals("partial") ? new BigDecimal("0.5") : BigDecimal.ONE,
            scenario.equals("open") ? BigDecimal.ONE : BigDecimal.ZERO,
            scenario.equals("price") ? BigDecimal.TEN : new BigDecimal("100"), new BigDecimal("100"),
            scenario.equals("rejected") ? "거절" : "", "FILLED");
    }
}
