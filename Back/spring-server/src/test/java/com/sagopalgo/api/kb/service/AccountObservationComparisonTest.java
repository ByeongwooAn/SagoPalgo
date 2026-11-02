package com.sagopalgo.api.kb.service;

import static com.sagopalgo.api.kb.service.AccountObservationComparisonFixtures.*;
import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse.*;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Section;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Completeness;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Issue;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class AccountObservationComparisonTest {
    private final AccountObservationComparison comparison = new AccountObservationComparison();

    @Test void unchangedObservationsReturnFourComparedEmptySections() {
        var result = comparison.compare(response(observation(0)),response(observation(1)));
        assertThat(result.status()).isEqualTo(ComparisonStatus.COMPARED);
        assertThat(result.readOnly()).isTrue(); assertThat(result.usableForTrading()).isFalse();
        assertThat(result.sections()).hasSize(4).allSatisfy(s -> {
            assertThat(s.reasons()).isEmpty(); assertThat(s.summaryChanges()).isEmpty(); assertThat(s.rowChanges()).isEmpty();
        });
    }

    @Test void calculatesExactFractionalAndLargeMoneyDeltasWithoutDouble() {
        var a = change(observation(0),0,s -> rows(s,row("is_no","005930","gnrl_q","0.123456")));
        var b = change(observation(1),0,s -> rows(s,row("is_no","005930","gnrl_q","0.123457")));
        a = change(a,1,s -> summary(s,Map.of("ordr_psbl_csh","999999999999999999999999.000001")));
        b = change(b,1,s -> summary(s,Map.of("ordr_psbl_csh","999999999999999999999998.999999")));
        var result = comparison.compare(response(a),response(b));
        var quantity = result.sections().get(0).rowChanges().get(0).fields().get(0);
        assertThat(quantity.numericDelta()).isEqualTo("0.000001");
        assertThat(quantity.beforeValue()).isEqualTo("0.123456");
        assertThat(result.sections().get(1).summaryChanges().get(0).numericDelta()).isEqualTo("-0.000002");
    }

    @Test void numericFormattingAndRowOrderingDoNotCreateChanges() {
        var a = change(observation(0),0,s -> rows(s,row("is_no","2","gnrl_q","+001.000"),row("is_no","1","gnrl_q","0")));
        var b = change(observation(1),0,s -> rows(s,row("is_no","1","gnrl_q","-0.0"),row("is_no","2","gnrl_q","1")));
        assertThat(comparison.compare(response(a),response(b)).sections().get(0).rowChanges()).isEmpty();
    }

    @Test void nullMissingAndZeroRemainDistinctAndUnknownDeltaIsNull() {
        var a = change(observation(0),0,s -> rows(s,row("is_no","1","gnrl_q",null)));
        var b = change(observation(1),0,s -> rows(s,row("is_no","1","gnrl_q","0","ordr_psbl_q",null)));
        var fields = comparison.compare(response(a),response(b)).sections().get(0).rowChanges().get(0).fields();
        assertThat(fields).hasSize(2);
        assertThat(fields.get(0).beforeValue()).isNull(); assertThat(fields.get(0).afterValue()).isEqualTo("0");
        assertThat(fields.get(0).numericDelta()).isNull();
        assertThat(fields.get(1).beforePresent()).isFalse(); assertThat(fields.get(1).afterPresent()).isTrue();
        assertThat(fields.get(1).afterValue()).isNull();
    }

    @Test void oneSidedRowsAreObservationsAndDoNotInferBuySellOrZeroBalances() {
        var a = change(observation(0),0,s -> rows(s,row("is_no","2")));
        var b = change(observation(1),0,s -> rows(s,row("is_no","1","gnrl_q","0.000001")));
        var changes = comparison.compare(response(a),response(b)).sections().get(0).rowChanges();
        assertThat(changes).extracting(RowChange::kind).containsExactly(RowChangeKind.OBSERVED_ONLY_AFTER,RowChangeKind.OBSERVED_ONLY_BEFORE);
        assertThat(changes.get(0).fields().get(0).numericDelta()).isNull();
        assertThat(changes.get(1).fields()).isEmpty();
    }

    @Test void reportsTextChangesAndOrderRemainingQuantityWithoutLifecycleDecisions() {
        var a = change(observation(0),3,s -> rows(s,row("ordr_no","1","stnd_is_no","005930","nccls_q","2","hngl_shrt_nm","old")));
        var b = change(observation(1),3,s -> rows(s,row("ordr_no","1","stnd_is_no","005930","nccls_q","0","hngl_shrt_nm","new")));
        var changes = comparison.compare(response(a),response(b)).sections().get(3).rowChanges();
        assertThat(changes).hasSize(1); assertThat(changes.get(0).kind()).isEqualTo(RowChangeKind.CHANGED);
        assertThat(changes.get(0).fields()).extracting(FieldChange::numericDelta).containsExactly(null,"-2");
    }

    @Test void compositeIdentityKeepsDifferentMarketsSeparate() {
        var before = identified(2,"005930");
        var fields = new LinkedHashMap<>(before.fields()); fields.put("fnl_ccls_excg_cd","NXT");
        var a = change(observation(0),2,s -> rows(s,before));
        var b = change(observation(1),2,s -> rows(s,new com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Row(fields)));
        assertThat(comparison.compare(response(a),response(b)).sections().get(2).rowChanges()).hasSize(2)
            .noneSatisfy(c -> assertThat(c.kind()).isEqualTo(RowChangeKind.CHANGED));
    }

    @ParameterizedTest @ValueSource(ints={0,1,2,3})
    void duplicateIdentityBlocksWholeSectionInsteadOfMerging(int index) {
        var a = change(observation(0),index,s -> rows(s,identified(index,"1"),identified(index,"1")));
        var result = comparison.compare(response(a),response(observation(1)));
        assertBlocked(result.sections().get(index),Reason.DUPLICATE_ROW_IDENTITY);
        assertThat(result.status()).isEqualTo(ComparisonStatus.PARTIAL);
    }

    @ParameterizedTest @ValueSource(ints={0,1,2,3})
    void missingIdentityBlocksSectionEvenIfOnlyOneRow(int index) {
        var a = change(observation(0),index,s -> rows(s,row("is_nm","unknown")));
        assertBlocked(comparison.compare(response(a),response(observation(1))).sections().get(index),Reason.INVALID_ROW_IDENTITY);
    }

    @Test void partialOrFailedSectionDoesNotHideOtherGoodSections() {
        var a = change(observation(0),0,s -> quality(s,Status.PARTIAL,Completeness.PARTIAL,List.of()));
        var b = change(observation(1),1,s -> quality(s,Status.FAILED,Completeness.UNKNOWN,List.of()));
        var result = comparison.compare(response(a),response(b));
        assertThat(result.status()).isEqualTo(ComparisonStatus.PARTIAL);
        assertBlocked(result.sections().get(0),Reason.SECTION_INCOMPLETE);
        assertBlocked(result.sections().get(1),Reason.SECTION_UNAVAILABLE);
        assertThat(result.sections().get(2).status()).isEqualTo(ComparisonStatus.COMPARED);
    }

    @Test void evenCompleteSectionWithIssuesIsBlockedAndIncludesSourceDiagnostics() {
        var a = change(observation(0),0,s -> quality(s,Status.SUCCESS,Completeness.COMPLETE,List.of(new Issue("INVALID_PROCESS_TIME","processTime"))));
        var s = comparison.compare(response(a),response(observation(1))).sections().get(0);
        assertBlocked(s,Reason.SECTION_HAS_ISSUES); assertThat(s.before().issues()).hasSize(1);
    }

    @Test void differentFiltersBlockOnlyAffectedSection() {
        var a = change(observation(0),0,s -> scope(s,Map.of("stockFilter","005930")));
        var result = comparison.compare(response(a),response(observation(1)));
        assertBlocked(result.sections().get(0),Reason.SCOPE_MISMATCH);
        assertThat(result.sections().get(1).status()).isEqualTo(ComparisonStatus.COMPARED);
    }

    @Test void differentOrderDaysCannotCompareOrdersButCanCompareBalances() {
        var b = change(observation(1),3,s -> scope(s,Map.of("orderDate","20261103","executionClassification","0")));
        var result = comparison.compare(response(observation(0)),response(b));
        assertBlocked(result.sections().get(3),Reason.SCOPE_MISMATCH);
        assertThat(result.sections().get(0).status()).isEqualTo(ComparisonStatus.COMPARED);
    }

    @ParameterizedTest @ValueSource(ints={-1,0})
    void reversedOrOverlappingObservationIntervalsBlockAllSections(int minute) {
        var result = comparison.compare(response(observation(0)),response(observation(minute)));
        assertThat(result.status()).isEqualTo(ComparisonStatus.BLOCKED);
        assertThat(result.sections()).allSatisfy(s -> assertBlocked(s,Reason.INTERVAL_NOT_FORWARD));
    }

    @ParameterizedTest @ValueSource(strings={"PENDING","FAILED"})
    void unfinishedStorageDoesNotBecomeAnEmptySuccessfulAccount(String state) {
        var pending = new AccountObservationResponse(UUID.randomUUID().toString(),"20261102",state,null,null,null,null,
            state.equals("FAILED") ? "OBSERVATION_FAILED" : null,true,null);
        var result = comparison.compare(pending,response(observation(1)));
        assertThat(result.status()).isEqualTo(ComparisonStatus.BLOCKED);
        assertThat(result.sections()).allSatisfy(s -> assertBlocked(s,Reason.STORAGE_NOT_COMPLETED));
    }

    @Test void rowCountContradictionIsBlockedEvenWithCompleteFlag() {
        var a = change(observation(0),0,s -> new Section(s.api(),s.scope(),s.status(),s.completeness(),s.startedAt(),s.completedAt(),null,
            1,1,1,s.summary(),List.of(),List.of()));
        assertBlocked(comparison.compare(response(a),response(observation(1))).sections().get(0),Reason.INVALID_ROW_COUNT);
    }

    @Test void unsupportedFieldsAreBlockedRatherThanReturned() {
        var a = change(observation(0),0,s -> rows(s,row("is_no","1","private-field","secret")));
        assertBlocked(comparison.compare(response(a),response(observation(1))).sections().get(0),Reason.UNSUPPORTED_FIELDS);
    }

    @ParameterizedTest @ValueSource(strings={"1e2","NaN","1,000"," ","1.2.3"})
    void malformedNumbersBlockCalculation(String value) {
        var a = change(observation(0),1,s -> summary(s,Map.of("tfnd",value)));
        assertBlocked(comparison.compare(response(a),response(observation(1))).sections().get(1),Reason.INVALID_NUMBER);
    }

    private Section quality(Section s, Status status, Completeness completeness, List<Issue> issues) {
        return new Section(s.api(),s.scope(),status,completeness,s.startedAt(),s.completedAt(),null,s.pagesRead(),
            s.receivedRowCount(),s.reportedTotalCount(),s.summary(),s.rows(),issues);
    }
    private void assertBlocked(SectionComparison s, Reason reason) {
        assertThat(s.status()).isEqualTo(ComparisonStatus.BLOCKED); assertThat(s.reasons()).contains(reason);
        assertThat(s.summaryChanges()).isEmpty(); assertThat(s.rowChanges()).isEmpty();
    }
}
