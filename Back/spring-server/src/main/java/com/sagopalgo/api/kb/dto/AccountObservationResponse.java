package com.sagopalgo.api.kb.dto;

import java.time.Instant;
import java.util.List;

/** DB 관찰 기록이며 거래 원장/주문 가능 판정이 아닙니다. */
public record AccountObservationResponse(
    String requestId, String orderDate, String storageState, String observationId,
    String snapshotStatus, Instant createdAt, Instant completedAt, String failureCode,
    boolean readOnly, KbAccountSnapshotResponse observation
) {
    public record Summary(
        String requestId, String orderDate, String storageState, String observationId,
        String snapshotStatus, Instant createdAt, Instant completedAt, String failureCode,
        boolean readOnly
    ) {}

    public record Page(List<Summary> items, Long nextBeforeId) {}
}
