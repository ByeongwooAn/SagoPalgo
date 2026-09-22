package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 최근 주문 사전검증 감사 로그 한 건입니다.
 */
public record OrderPrecheckHistoryItemResponse(
    Long orderPrecheckId,
    String stockCode,
    String stockName,
    String market,
    String side,
    BigDecimal limitPrice,
    BigDecimal quantity,
    BigDecimal estimatedAmount,
    String quoteProvider,
    BigDecimal currentPrice,
    boolean orderEnabled,
    boolean eligible,
    String blockerSummary,
    LocalDateTime checkedAt
) {
}
