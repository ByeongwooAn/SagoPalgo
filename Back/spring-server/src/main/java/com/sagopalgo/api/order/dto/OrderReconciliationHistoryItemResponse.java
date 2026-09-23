package com.sagopalgo.api.order.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record OrderReconciliationHistoryItemResponse(
    Long checkId,
    LocalDate orderDate,
    String orderNo,
    boolean completeScan,
    int pagesScanned,
    int matchCount,
    String reviewStatus,
    LocalDateTime checkedAt
) {
}
