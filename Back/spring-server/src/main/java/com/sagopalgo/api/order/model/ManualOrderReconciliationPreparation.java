package com.sagopalgo.api.order.model;

import java.time.LocalDateTime;

public record ManualOrderReconciliationPreparation(
    String commandId, Long userId, String accountFingerprint, String orderNo,
    String tokenHash, LocalDateTime expiresAt, LocalDateTime checkedAt
) {}
