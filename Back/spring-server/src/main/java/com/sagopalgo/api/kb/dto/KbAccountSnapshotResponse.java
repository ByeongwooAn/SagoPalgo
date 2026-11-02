package com.sagopalgo.api.kb.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;
import java.util.List;
import java.util.Map;

/** 읽기 전용 관찰 계약. 금액/수량은 십진 문자열이며 주문 가능 판정이나 원장이 아닙니다. */
public record KbAccountSnapshotResponse(
    String contractVersion,
    String observationId,
    String provider,
    String accountAlias,
    Instant startedAt,
    Instant completedAt,
    Status status,
    boolean atomic,
    boolean usableForTrading,
    List<Section> sections
) {
    public enum Status { SUCCESS, PARTIAL, FAILED, DISABLED }
    public enum Completeness { COMPLETE, PARTIAL, UNKNOWN, INVALID }

    public record Issue(String code, String field) {}

    public record Section(
        String api,
        Map<String, String> scope,
        Status status,
        Completeness completeness,
        Instant startedAt,
        Instant completedAt,
        String providerProcessTime,
        int pagesRead,
        int receivedRowCount,
        Integer reportedTotalCount,
        @JsonInclude(value = JsonInclude.Include.ALWAYS, content = JsonInclude.Include.ALWAYS)
        Map<String, String> summary,
        List<Row> rows,
        List<Issue> issues
    ) {}

    /** 공식 필드 allowlist만 보관합니다. 원본 계좌/인증값·응답 전문은 포함하지 않습니다. */
    public record Row(
        @JsonInclude(value = JsonInclude.Include.ALWAYS, content = JsonInclude.Include.ALWAYS)
        Map<String, String> fields
    ) {}
}
