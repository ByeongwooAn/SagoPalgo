package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * 주문 가능 자원과 안전 조건을 계산한 결과입니다.
 */
public record OrderPrecheckResponse(
    Long orderPrecheckId,
    String stockCode,
    String stockName,
    String market,
    String side,
    String orderType,
    BigDecimal limitPrice,
    BigDecimal quantity,
    BigDecimal estimatedAmount,
    String quoteProvider,
    BigDecimal currentPrice,
    BigDecimal priceDeviationRate,
    BigDecimal orderAvailableCash,
    BigDecimal orderableQuantity,
    BigDecimal maxOrderAmount,
    BigDecimal maxPriceDeviationRate,
    boolean orderEnabled,
    boolean eligible,
    boolean canSubmit,
    String submissionMessage,
    List<OrderSafetyCheckResponse> checks,
    LocalDateTime checkedAt
) {
}
