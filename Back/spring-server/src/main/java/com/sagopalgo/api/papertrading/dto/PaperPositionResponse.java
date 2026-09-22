package com.sagopalgo.api.papertrading.dto;

import java.math.BigDecimal;

/**
 * 아직 청산하지 않은 종목별 가상 포지션입니다.
 */
public record PaperPositionResponse(
    String stockCode,
    String stockName,
    String market,
    String provider,
    BigDecimal quantity,
    BigDecimal averagePrice,
    BigDecimal currentPrice,
    BigDecimal valuationAmount,
    BigDecimal unrealizedProfit,
    BigDecimal profitRate
) {
}
