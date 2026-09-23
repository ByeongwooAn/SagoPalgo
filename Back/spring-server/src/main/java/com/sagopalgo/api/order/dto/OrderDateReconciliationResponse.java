package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public record OrderDateReconciliationResponse(
    Long checkId,
    Long approvalId,
    String guardStatus,
    String stockCode,
    String orderSide,
    BigDecimal requestedPrice,
    BigDecimal quantity,
    String orderDate,
    boolean completeScan,
    int pagesScanned,
    boolean itemLimitReached,
    List<KbOrderExecutionItemResponse> items,
    LocalDateTime checkedAt
) {
}
