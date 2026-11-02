package com.sagopalgo.api.kb.model;

import java.time.LocalDateTime;

/** 사용자/연결 내부 지문은 응답 DTO로 직접 노출하지 않습니다. */
public record AccountObservationCollectorRecord(Long userId, String accountBinding, String state,
    String activeRequestId, String activeOrderDate, String lastRequestId, String lastStorageState,
    String lastSnapshotStatus, String failureCode, LocalDateTime nextDueAt,
    LocalDateTime startedAt, LocalDateTime completedAt) {}
