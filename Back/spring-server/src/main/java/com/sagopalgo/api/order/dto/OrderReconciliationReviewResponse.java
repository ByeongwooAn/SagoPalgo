package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

public record OrderReconciliationReviewResponse(
    Long checkId,
    Long approvalId,
    String guardStatus,
    String stockCode,
    String orderSide,
    BigDecimal requestedPrice,
    BigDecimal quantity,
    String orderDate,
    String orderNo,
    boolean completeScan,
    int pagesScanned,
    String reviewStatus,
    List<KbOrderExecutionItemResponse> matches,
    LocalDateTime checkedAt
) {
}
