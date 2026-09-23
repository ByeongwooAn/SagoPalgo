package com.sagopalgo.api.order.dto;

import java.time.LocalDate;
import java.time.LocalDateTime;

public record OrderDateReconciliationHistoryItemResponse(
    Long checkId,
    LocalDate orderDate,
    boolean completeScan,
    int pagesScanned,
    int rowCount,
    boolean itemLimitReached,
    LocalDateTime checkedAt
) {
}
