package com.sagopalgo.api.order.dto;

import java.time.LocalDateTime;

public record OrderApprovalPrepareResponse(
    Long approvalId,
    String token,
    LocalDateTime expiresAt,
    OrderPrecheckResponse precheck,
    String message
) {
}
