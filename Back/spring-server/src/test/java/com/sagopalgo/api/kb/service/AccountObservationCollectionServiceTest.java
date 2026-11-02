package com.sagopalgo.api.kb.service;

import static com.sagopalgo.api.kb.service.AccountObservationFixtures.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.AccountObservationCollectionProperties;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.model.AccountObservationCollectorRecord;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.concurrent.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.EnumSource;
import org.junit.jupiter.params.provider.ValueSource;

class AccountObservationCollectionServiceTest {
    private final AccountObservationCollectorStore store=mock(AccountObservationCollectorStore.class);
    private final AccountObservationHistoryService history=mock(AccountObservationHistoryService.class);
    private final AccountObservationBinding binding=mock(AccountObservationBinding.class);
    private final SecuritiesProviderProperties providers=properties();
    private final String scope="b".repeat(64);
    private final String request="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
    private final Clock clock=Clock.fixed(Instant.parse("2026-11-01T16:00:00Z"),ZoneOffset.UTC);
    private AccountObservationCollectionService service;

    @BeforeEach void setup() {
        service=service(true,true,1L);
        when(binding.current()).thenReturn(scope);when(binding.matches(scope)).thenReturn(true);
        when(store.claim(eq(1L),eq(scope),anyString(),eq(DATE))).thenAnswer(call ->
            new AccountObservationCollectorStore.Claim(active(call.getArgument(2)),true));
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenAnswer(call -> result(call.getArgument(1),Status.SUCCESS));
    }

    @Test void disabledPolicyDoesNotReadDbBindingOrKb() {
        service(false,true,1L).collectDue();verifyNoInteractions(store,binding,history);
    }
    @Test void disabledPersonalModeOrInvalidUserDoesNotReadDb() {
        service(true,false,1L).collectDue();service(true,true,null).collectDue();service(true,true,0L).collectDue();
        verifyNoInteractions(store,binding,history);
    }
    @Test void accountDisabledDoesNotReadDbOrKb() {
        providers.getKb().setAccountEnabled(false);service.collectDue();verifyNoInteractions(store,binding,history);
    }
    @Test void missingCredentialsCannotReserveOrQuery() {
        when(binding.current()).thenThrow(new ApiException(ErrorCode.VALIDATION_ERROR));
        service.collectDue();verifyNoInteractions(store,history);
    }
    @Test void startsOnlyAfterDurableClaimWithKoreanDate() {
        service.collectDue();
        var ordered=inOrder(store,history);
        ordered.verify(store).claim(eq(1L),eq(scope),matches("[0-9a-f-]{36}"),eq("20261102"));
        ordered.verify(history).captureForBinding(eq(1L),anyString(),eq("20261102"),eq(scope));
        ordered.verify(store).finish(eq(1L),eq(scope),anyString(),eq(DATE),eq("COMPLETED"),eq("SUCCESS"),isNull(),eq(900));
    }
    @Test void storageFailureBeforeClaimNeverCallsHistory() {
        when(store.claim(anyLong(),anyString(),anyString(),anyString())).thenThrow(new ApiException(ErrorCode.OBSERVATION_COLLECTION_STORAGE_UNAVAILABLE));
        service.collectDue();verifyNoInteractions(history);
    }
    @ParameterizedTest @ValueSource(strings={"IDLE","PAUSED"})
    void anotherOwnerOrCooldownDoesNotStartCapture(String state) {
        when(store.claim(anyLong(),anyString(),anyString(),anyString())).thenReturn(new AccountObservationCollectorStore.Claim(record(state),false));
        service.collectDue();verifyNoInteractions(history);
    }
    @Test void existingActiveRequestReadsOnlyStoredResult() {
        when(store.claim(anyLong(),anyString(),anyString(),anyString())).thenReturn(new AccountObservationCollectorStore.Claim(active(request),false));
        when(history.detailForBinding(1L,request,scope)).thenReturn(result(request,Status.SUCCESS));
        service.collectDue();verify(history).detailForBinding(1L,request,scope);
        verify(history,never()).captureForBinding(anyLong(),anyString(),anyString(),anyString());
        verify(store).finish(1L,scope,request,DATE,"COMPLETED","SUCCESS",null,900);
    }
    @Test void pendingOrMissingActiveReceiptNeverExpiresOrRecaptures() {
        when(store.claim(anyLong(),anyString(),anyString(),anyString())).thenReturn(new AccountObservationCollectorStore.Claim(active(request),false));
        var pending=new AccountObservationResponse(request,DATE,"PENDING",null,null,clock.instant(),null,null,true,null);
        when(history.detailForBinding(1L,request,scope)).thenReturn(pending).thenThrow(new ApiException(ErrorCode.RESOURCE_NOT_FOUND));
        service.collectDue();service.collectDue();
        verify(store,never()).finish(anyLong(),anyString(),anyString(),anyString(),anyString(),any(),any(),anyInt());
        verify(history,never()).captureForBinding(anyLong(),anyString(),anyString(),anyString());
    }
    @ParameterizedTest @EnumSource(value=Status.class,names={"PARTIAL","FAILED","DISABLED"})
    void nonSuccessfulSnapshotPausesInsteadOfAutomaticallyLooping(Status status) {
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenAnswer(c -> result(c.getArgument(1),status));
        service.collectDue();verify(store).finish(eq(1L),eq(scope),anyString(),eq(DATE),eq("COMPLETED"),eq(status.name()),eq("SNAPSHOT_"+status.name()),eq(900));
    }
    @Test void failedStorageReceiptPausesWithFixedCode() {
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenAnswer(c ->
            new AccountObservationResponse(c.getArgument(1),DATE,"FAILED",null,null,clock.instant(),clock.instant(),"CONTEXT_CHANGED",true,null));
        service.collectDue();verify(store).finish(eq(1L),eq(scope),anyString(),eq(DATE),eq("FAILED"),isNull(),eq("CONTEXT_CHANGED"),eq(900));
    }
    @Test void unexpectedCaptureOrFinalWriteFailureKeepsClaimWithoutRetry() {
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenThrow(new IllegalStateException("private exception"));
        service.collectDue();verify(history,times(1)).captureForBinding(anyLong(),anyString(),anyString(),anyString());
        verify(store,never()).finish(anyLong(),anyString(),anyString(),anyString(),anyString(),any(),any(),anyInt());
    }
    @Test void mismatchedReceiptCannotReleaseClaim() {
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenReturn(result(request,Status.SUCCESS));
        service.collectDue();verify(store,never()).finish(anyLong(),anyString(),anyString(),anyString(),anyString(),any(),any(),anyInt());
    }
    @Test void concurrentCallsInOneProcessDoNotDuplicateClaim() throws Exception {
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var executor=Executors.newSingleThreadExecutor();
        when(history.captureForBinding(eq(1L),anyString(),eq(DATE),eq(scope))).thenAnswer(call -> {
            entered.countDown();if(!release.await(10,TimeUnit.SECONDS)) throw new AssertionError("timeout");
            return result(call.getArgument(1),Status.SUCCESS);
        });
        try {
            var task=executor.submit(service::collectDue);assertThat(entered.await(10,TimeUnit.SECONDS)).isTrue();
            service.collectDue();release.countDown();task.get(10,TimeUnit.SECONDS);
        } finally {release.countDown();executor.shutdownNow();}
        verify(store,times(1)).claim(anyLong(),anyString(),anyString(),anyString());
    }
    @Test void statusIsReadOnlyScopedAndDoesNotExposeInternalIdentity() throws Exception {
        when(store.find(1L,scope)).thenReturn(active(request));
        var response=service.status(1L);
        assertThat(response.state()).isEqualTo("ACTIVE");assertThat(response.readOnly()).isTrue();assertThat(response.usableForTrading()).isFalse();
        assertThat(new ObjectMapper().findAndRegisterModules().writeValueAsString(response)).doesNotContain(scope,"accountBinding","userId","private-key");
        verifyNoInteractions(history);verify(store,never()).claim(anyLong(),anyString(),anyString(),anyString());
    }
    @Test void unconfiguredStatusDoesNotTouchCollectorDb() {
        when(binding.current()).thenThrow(new ApiException(ErrorCode.VALIDATION_ERROR));
        assertThat(service.status(1L).state()).isEqualTo("UNCONFIGURED");verifyNoInteractions(store,history);
    }
    @Test void statusRejectsBindingChangesDuringRead() {
        when(binding.matches(scope)).thenReturn(false);
        assertError(() -> service.status(1L),ErrorCode.DUPLICATE_RESOURCE);
    }
    @ParameterizedTest @ValueSource(strings={"ACTIVE","IDLE"})
    void resumeNeverClearsActiveOrIdleRecords(String state) {
        when(store.find(1L,scope)).thenReturn(record(state));
        assertError(() -> service.resume(1L,request),ErrorCode.DUPLICATE_RESOURCE);verifyNoInteractions(history);
    }
    @Test void resumeValidatesExactPausedReceiptThenSchedulesWithoutCapturing() {
        when(store.find(1L,scope)).thenReturn(record("PAUSED"),record("IDLE"));
        when(history.detailForBinding(1L,request,scope)).thenReturn(result(request,Status.PARTIAL));
        assertThat(service.resume(1L,request).state()).isEqualTo("IDLE");
        verify(store).resume(1L,scope,request,900);verify(history,never()).captureForBinding(anyLong(),anyString(),anyString(),anyString());
    }
    @Test void tamperedReceiptCannotResume() {
        when(store.find(1L,scope)).thenReturn(record("PAUSED"));
        when(history.detailForBinding(1L,request,scope)).thenThrow(new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        assertError(() -> service.resume(1L,request),ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE);
        verify(store,never()).resume(anyLong(),anyString(),anyString(),anyInt());
    }
    @Test void invalidUserAndRequestAreRejectedBeforeIo() {
        assertError(() -> service.status(0L),ErrorCode.VALIDATION_ERROR);
        assertError(() -> service.resume(1L,"bad"),ErrorCode.VALIDATION_ERROR);verifyNoInteractions(store,binding,history);
    }

    private AccountObservationCollectionService service(boolean enabled,boolean personalEnabled,Long user) {
        return new AccountObservationCollectionService(new AccountObservationCollectionProperties(enabled,900),
            new PersonalModeProperties(personalEnabled,user,"owner","local@test"),providers,binding,store,history,clock);
    }
    private AccountObservationCollectorRecord active(String id) {
        return new AccountObservationCollectorRecord(1L,scope,"ACTIVE",id,DATE,null,null,null,null,NOW,NOW,null);
    }
    private AccountObservationCollectorRecord record(String state) {
        return new AccountObservationCollectorRecord(1L,scope,state,state.equals("ACTIVE") ? request : null,
            state.equals("ACTIVE") ? DATE : null,request,"COMPLETED","PARTIAL",state.equals("PAUSED") ? "SNAPSHOT_PARTIAL" : null,NOW,NOW,NOW);
    }
    private AccountObservationResponse result(String id,Status status) {
        KbAccountSnapshotResponse snapshot=snapshot(status);
        return new AccountObservationResponse(id,DATE,"COMPLETED",snapshot.observationId(),status.name(),clock.instant(),clock.instant(),null,true,snapshot);
    }
    private void assertError(Runnable action,ErrorCode code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(code));
    }
}
