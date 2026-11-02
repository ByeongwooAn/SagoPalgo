package com.sagopalgo.api.kb.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Completeness;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Issue;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** 관찰 간 필드 차이이며 거래·현금흐름·주문 종결 판정이 아닙니다. */
public record AccountObservationComparisonResponse(
    String contractVersion, Reference before, Reference after, ComparisonStatus status,
    boolean readOnly, boolean usableForTrading, List<SectionComparison> sections
) {
    public enum ComparisonStatus { COMPARED, PARTIAL, BLOCKED }
    public enum Reason {
        STORAGE_NOT_COMPLETED, INTERVAL_NOT_FORWARD, SCOPE_MISMATCH,
        SECTION_UNAVAILABLE, SECTION_INCOMPLETE, SECTION_HAS_ISSUES,
        INVALID_ROW_COUNT, INVALID_ROW_IDENTITY, DUPLICATE_ROW_IDENTITY,
        UNSUPPORTED_FIELDS, INVALID_NUMBER
    }
    public enum RowChangeKind { CHANGED, OBSERVED_ONLY_BEFORE, OBSERVED_ONLY_AFTER }

    public record Reference(String requestId, String orderDate, String storageState,
        String observationId, String snapshotStatus, String failureCode, Instant startedAt, Instant completedAt) {}

    public record SourceInfo(Status status, Completeness completeness, Instant startedAt, Instant completedAt,
        int receivedRowCount, Integer reportedTotalCount, List<Issue> issues) {}

    public record SectionComparison(String api, Map<String,String> beforeScope, Map<String,String> afterScope,
        SourceInfo before, SourceInfo after, ComparisonStatus status, List<Reason> reasons,
        List<FieldChange> summaryChanges, List<RowChange> rowChanges) {}

    @JsonInclude(JsonInclude.Include.ALWAYS)
    public record FieldChange(String field, boolean beforePresent, boolean afterPresent,
        String beforeValue, String afterValue, String numericDelta) {}

    public record RowChange(RowChangeKind kind, Map<String,String> identity, List<FieldChange> fields) {}
}
