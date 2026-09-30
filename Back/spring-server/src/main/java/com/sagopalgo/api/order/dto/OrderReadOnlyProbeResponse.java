package com.sagopalgo.api.order.dto;

import java.time.LocalDateTime;

public record OrderReadOnlyProbeResponse(
    String status,
    String orderDate,
    LocalDateTime checkedAt,
    boolean readOnly,
    String message
) {
}
