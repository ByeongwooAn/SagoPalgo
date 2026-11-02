package com.sagopalgo.api.kb.dto;

import java.time.Instant;

public record AccountObservationCollectionResponse(boolean enabled, boolean personalModeEnabled,
    boolean accountEnabled, boolean connectionConfigured, int intervalSeconds, String state,
    String activeRequestId, String activeOrderDate, String lastRequestId, String lastStorageState,
    String lastSnapshotStatus, String failureCode, Instant nextDueAt, Instant startedAt, Instant completedAt,
    boolean readOnly, boolean usableForTrading) {}
