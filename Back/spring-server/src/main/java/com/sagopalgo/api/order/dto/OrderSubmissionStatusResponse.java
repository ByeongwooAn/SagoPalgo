package com.sagopalgo.api.order.dto;

import java.time.LocalDateTime;

public record OrderSubmissionStatusResponse(
    Long approvalId,
    String status,
    LocalDateTime expiresAt,
    LocalDateTime reservedAt,
    LocalDateTime uncertainAt
) {
}
