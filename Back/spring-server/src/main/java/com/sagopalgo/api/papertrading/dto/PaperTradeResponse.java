package com.sagopalgo.api.papertrading.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 화면에 표시할 단일 모의매매 체결 기록입니다.
 */
public record PaperTradeResponse(
    Long tradeRecordId,
    Long recommendationId,
    String stockCode,
    String stockName,
    String market,
    String tradeType,
    BigDecimal tradePrice,
    BigDecimal quantity,
    BigDecimal tradeAmount,
    BigDecimal realizedProfit,
    LocalDateTime tradeDate,
    String memo
) {
}
