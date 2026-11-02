package com.sagopalgo.api.kb.service;

import static com.sagopalgo.api.kb.service.AccountObservationComparisonFixtures.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.kb.controller.AccountObservationComparisonController;
import com.sagopalgo.api.kb.controller.AccountObservationHistoryController;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse.ComparisonStatus;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class AccountObservationComparisonServiceTest {
    private final AccountObservationHistoryService history = mock(AccountObservationHistoryService.class);
    private final AccountObservationBinding binding = mock(AccountObservationBinding.class);
    private final AccountObservationComparison comparison = spy(new AccountObservationComparison());
    private final AccountObservationComparisonService service = new AccountObservationComparisonService(history,binding,comparison);
    private final AccountObservationResponse before = response(observation(0));
    private final AccountObservationResponse after = response(observation(1));

    @BeforeEach void setup() {
        when(binding.current()).thenReturn("scope"); when(binding.matches("scope")).thenReturn(true);
        when(history.detail(1L,before.requestId())).thenReturn(before);
        when(history.detail(1L,after.requestId())).thenReturn(after);
    }

    @Test void readsOnlyStoredDetailsInRequestedDirectionAndNormalizesIds() {
        var result = service.compare(1L,before.requestId().toUpperCase(),after.requestId());
        assertThat(result.status()).isEqualTo(ComparisonStatus.COMPARED);
        var ordered = inOrder(history,comparison);
        ordered.verify(history).detail(1L,before.requestId()); ordered.verify(history).detail(1L,after.requestId());
        ordered.verify(comparison).compare(before,after); verifyNoMoreInteractions(history);
    }

    @ParameterizedTest @NullAndEmptySource @ValueSource(strings={"bad","1-1-1-1-1"})
    void validatesBothIdsBeforeAnyHistoryRead(String bad) {
        invalid(() -> service.compare(1L,before.requestId(),bad));
        invalid(() -> service.compare(1L,bad,after.requestId()));
        verifyNoInteractions(history,binding,comparison);
    }

    @Test void sameNormalizedIdIsRejectedWithoutReadingHistory() {
        invalid(() -> service.compare(1L,before.requestId(),before.requestId().toUpperCase()));
        verifyNoInteractions(history,binding,comparison);
    }

    @Test void missingLocalUserIsRejectedBeforeReadingHistory() {
        invalid(() -> service.compare(null,before.requestId(),after.requestId()));
        invalid(() -> service.compare(0L,before.requestId(),after.requestId()));
        verifyNoInteractions(history,binding,comparison);
    }

    @Test void missingOrOtherNamespaceRecordPreservesNotFound() {
        when(history.detail(1L,before.requestId())).thenThrow(new ApiException(ErrorCode.RESOURCE_NOT_FOUND));
        assertError(() -> service.compare(1L,before.requestId(),after.requestId()),ErrorCode.RESOURCE_NOT_FOUND);
        verify(history,never()).detail(1L,after.requestId()); verifyNoInteractions(comparison);
    }

    @Test void checksumStorageFailureDoesNotReturnPartialComparison() {
        when(history.detail(1L,after.requestId())).thenThrow(new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        assertError(() -> service.compare(1L,before.requestId(),after.requestId()),ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE);
        verifyNoInteractions(comparison);
    }

    @Test void changedBindingAfterFirstReadPreventsSecondRead() {
        when(binding.matches("scope")).thenReturn(false);
        assertError(() -> service.compare(1L,before.requestId(),after.requestId()),ErrorCode.DUPLICATE_RESOURCE);
        verify(history,never()).detail(1L,after.requestId()); verifyNoInteractions(comparison);
    }

    @Test void changedBindingBetweenReadsPreventsComparisonOfTwoAccounts() {
        when(binding.matches("scope")).thenReturn(true,false);
        assertError(() -> service.compare(1L,before.requestId(),after.requestId()),ErrorCode.DUPLICATE_RESOURCE);
        verifyNoInteractions(comparison);
    }

    @Test void changedBindingDuringComparisonPreventsResponse() {
        when(binding.matches("scope")).thenReturn(true,true,false);
        assertError(() -> service.compare(1L,before.requestId(),after.requestId()),ErrorCode.DUPLICATE_RESOURCE);
        verify(comparison).compare(before,after);
    }

    @Test void fixedComparisonRouteCoexistsWithDetailAndReturnsNoStore() throws Exception {
        var context = new LocalUserContext(new PersonalModeProperties(true,1L,"owner","local@test"));
        var mvc = MockMvcBuilders.standaloneSetup(new AccountObservationComparisonController(service,context),
            new AccountObservationHistoryController(history,context)).setControllerAdvice(new GlobalExceptionHandler()).build();
        mvc.perform(get("/api/v1/kb/accounts/primary/observations/comparison")
            .param("beforeRequestId",before.requestId()).param("afterRequestId",after.requestId()))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
            .andExpect(jsonPath("$.data.contractVersion").value("KB_ACCOUNT_COMPARISON_V1"))
            .andExpect(jsonPath("$.data.readOnly").value(true)).andExpect(jsonPath("$.data.usableForTrading").value(false));
        mvc.perform(get("/api/v1/kb/accounts/primary/observations/"+before.requestId()))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.requestId").value(before.requestId()));
        mvc.perform(get("/api/v1/kb/accounts/primary/observations/comparison"))
            .andExpect(status().isBadRequest()).andExpect(jsonPath("$.error.code").value("VALIDATION_ERROR"));
        verify(history,never()).detail(1L,"comparison");
    }

    private void invalid(Runnable action) { assertError(action,ErrorCode.VALIDATION_ERROR); }
    private void assertError(Runnable action, ErrorCode code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(code));
    }
}
