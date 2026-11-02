package com.sagopalgo.api.kb.model;

import java.time.LocalDateTime;

/** 내부 저장 모델. 연결 지문·payload/hash는 API 응답 모델에 직접 노출하지 않습니다. */
public record AccountObservationRecord(
    Long id, Long userId, String requestId, String accountBinding, String orderDate,
    String storageState, String observationId, String snapshotStatus, String payload,
    String payloadSha256, String failureCode, LocalDateTime createdAt, LocalDateTime completedAt
) {}
