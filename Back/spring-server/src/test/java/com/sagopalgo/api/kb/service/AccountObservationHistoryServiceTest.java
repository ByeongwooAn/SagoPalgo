package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static com.sagopalgo.api.kb.service.AccountObservationFixtures.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class AccountObservationHistoryServiceTest {
    @Test void collectorBindingMismatchCannotReserveObserveOrReadAnotherScope() {
        assertThatThrownBy(() -> service.captureForBinding(1L,request,DATE,"another-scope"))
            .isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.DUPLICATE_RESOURCE));
        assertThatThrownBy(() -> service.detailForBinding(1L,request,"another-scope"))
            .isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.DUPLICATE_RESOURCE));
        verifyNoInteractions(store,observer);
    }
    private final AccountObservationStore store = mock(AccountObservationStore.class);
    private final AccountObservationBinding binding = mock(AccountObservationBinding.class);
    private final KbAccountSnapshotService observer = mock(KbAccountSnapshotService.class);
    private final AccountObservationCodec codec = new AccountObservationCodec(new ObjectMapper().findAndRegisterModules());
    private final String request = UUID.randomUUID().toString();
    private final String scope = "scope";
    private AccountObservationHistoryService service;

    @BeforeEach void setup() {
        service = new AccountObservationHistoryService(store,binding,observer,codec);
        when(binding.current()).thenReturn(scope); when(binding.matches(scope)).thenReturn(true);
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenReturn(new AccountObservationStore.Reservation(pending(request,scope),true));
    }

    @Test void capturesOnlyAfterCommittedReservationAndPreservesPartialPrecision() {
        var snapshot = snapshot(Status.PARTIAL);
        when(observer.observe(DATE)).thenReturn(snapshot);
        when(store.complete(eq(1L),eq(request),eq(scope),eq(snapshot.observationId()),eq("PARTIAL"),any(),any()))
            .thenReturn(completed(request,scope,snapshot,codec));
        var result = service.capture(1L,request,DATE);
        assertThat(result.storageState()).isEqualTo("COMPLETED");
        assertThat(result.snapshotStatus()).isEqualTo("PARTIAL");
        assertThat(result.readOnly()).isTrue();
        assertThat(result.observation().sections().get(2).rows().get(0).fields())
            .containsEntry("hld_q_p6","0.123456").containsEntry("now_prc",null);
        var ordered = inOrder(store,observer);
        ordered.verify(store).reserve(eq(1L),eq(request),eq(scope),eq(DATE),any());
        ordered.verify(observer).observe(DATE);
        ordered.verify(store).complete(eq(1L),eq(request),eq(scope),eq(snapshot.observationId()),eq("PARTIAL"),any(),any());
    }

    @Test void repeatedCompletedRequestReadsWithoutRecapturing() {
        var saved = completed(request,scope,snapshot(Status.SUCCESS),codec);
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenReturn(new AccountObservationStore.Reservation(saved,false));
        assertThat(service.capture(1L,request,DATE).observation()).isNotNull();
        verifyNoInteractions(observer);
    }

    @Test void pendingAfterInterruptedCaptureRemainsPendingWithoutRetry() {
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenReturn(new AccountObservationStore.Reservation(pending(request,scope),false));
        var result = service.capture(1L,request,DATE);
        assertThat(result.storageState()).isEqualTo("PENDING");
        assertThat(result.observation()).isNull();
        verifyNoInteractions(observer);
    }

    @Test void duplicateRequestCannotSwitchAccountOrOrderDate() {
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenReturn(new AccountObservationStore.Reservation(pending(request,"other-scope"),false));
        assertThatThrownBy(() -> service.capture(1L,request,DATE)).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.DUPLICATE_RESOURCE));
        verifyNoInteractions(observer);
    }

    @Test void databaseUnavailableBeforeReservationCannotTriggerBrokerRead() {
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenThrow(new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        assertThatThrownBy(() -> service.capture(1L,request,DATE)).isInstanceOf(ApiException.class);
        verifyNoInteractions(observer);
    }

    @Test void failedFinalSaveLeavesPendingAndSameIdDoesNotReadBrokerAgain() {
        var snapshot = snapshot(Status.SUCCESS);
        when(observer.observe(DATE)).thenReturn(snapshot);
        when(store.complete(eq(1L),eq(request),eq(scope),anyString(),anyString(),any(),any()))
            .thenThrow(new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        assertThatThrownBy(() -> service.capture(1L,request,DATE)).isInstanceOf(ApiException.class);
        when(store.reserve(eq(1L),eq(request),eq(scope),eq(DATE),any()))
            .thenReturn(new AccountObservationStore.Reservation(pending(request,scope),false));
        assertThat(service.capture(1L,request,DATE).storageState()).isEqualTo("PENDING");
        verify(observer,times(1)).observe(DATE);
    }

    @Test void connectionChangeDropsPayloadAndStoresOnlyFixedFailureCode() {
        when(observer.observe(DATE)).thenReturn(snapshot(Status.SUCCESS));
        when(binding.matches(scope)).thenReturn(true,false);
        when(store.fail(eq(1L),eq(request),eq(scope),eq("CONTEXT_CHANGED"),any())).thenReturn(failed("CONTEXT_CHANGED"));
        var result = service.capture(1L,request,DATE);
        assertThat(result.failureCode()).isEqualTo("CONTEXT_CHANGED");
        assertThat(result.observation()).isNull();
        verify(store,never()).complete(any(),any(),any(),any(),any(),any(),any());
    }

    @Test void unexpectedFailureDoesNotStoreExceptionOrSecret() throws Exception {
        when(observer.observe(DATE)).thenThrow(new IllegalStateException("private-token raw-account"));
        when(store.fail(eq(1L),eq(request),eq(scope),eq("OBSERVATION_FAILED"),any())).thenReturn(failed("OBSERVATION_FAILED"));
        var result = service.capture(1L,request,DATE);
        assertThat(new ObjectMapper().findAndRegisterModules().writeValueAsString(result)).doesNotContain("private-token","raw-account");
        assertThat(result.storageState()).isEqualTo("FAILED");
    }

    @Test void historyIsScopedAndUsesKeysetWithoutBrokerRead() {
        var one = pending(request,scope);
        var two = new AccountObservationRecord(2L,1L,UUID.randomUUID().toString(),scope,DATE,
            "PENDING",null,null,null,null,null,NOW,null);
        when(store.recent(1L,scope,null,2)).thenReturn(List.of(two,one));
        var page = service.history(1L,null,1);
        assertThat(page.items()).hasSize(1); assertThat(page.nextBeforeId()).isEqualTo(2L);
        assertThat(page.items().get(0).requestId()).isEqualTo(two.requestId());
        verifyNoInteractions(observer);
    }

    @Test void detailHasNoFallbackToOtherUserOrAccount() {
        when(store.find(1L,scope,request)).thenReturn(null);
        assertThatThrownBy(() -> service.detail(1L,request)).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
        verifyNoInteractions(observer);
    }

    @Test void accountChangeDuringHistoryReadCannotReturnOldScope() {
        when(store.recent(1L,scope,null,21)).thenReturn(List.of()); when(binding.matches(scope)).thenReturn(false);
        assertThatThrownBy(() -> service.history(1L,null,20)).isInstanceOf(ApiException.class);
    }

    @ParameterizedTest @ValueSource(strings={"20260230","2026-11-02","","20261102 "})
    void invalidDateHasNoDatabaseOrBrokerSideEffects(String date) {
        assertThatThrownBy(() -> service.capture(1L,request,date)).isInstanceOf(ApiException.class);
        verifyNoInteractions(store,observer,binding);
    }

    @ParameterizedTest @ValueSource(strings={"1-1-1-1-1","","not-a-uuid"})
    void invalidRequestIdHasNoIo(String id) {
        assertThatThrownBy(() -> service.capture(1L,id,DATE)).isInstanceOf(ApiException.class);
        verifyNoInteractions(store,observer,binding);
    }

    @Test void invalidHistoryBoundsHaveNoIo() {
        assertThatThrownBy(() -> service.history(1L,0L,20)).isInstanceOf(ApiException.class);
        assertThatThrownBy(() -> service.history(1L,null,101)).isInstanceOf(ApiException.class);
        verifyNoInteractions(store,observer,binding);
    }

    private AccountObservationRecord failed(String code) {
        return new AccountObservationRecord(1L,1L,request,scope,DATE,"FAILED",null,null,null,null,code,NOW,NOW);
    }
}
