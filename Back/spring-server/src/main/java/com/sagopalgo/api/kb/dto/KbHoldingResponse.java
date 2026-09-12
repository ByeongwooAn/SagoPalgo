package com.sagopalgo.api.kb.dto;

import java.math.BigDecimal;

/**
 * KB증권 보유 주식 한 줄을 앱 내부 표준 형태로 정규화한 응답입니다.
 */
public record KbHoldingResponse(
    String stockCode,
    String stockName,
    String market,
    BigDecimal quantity,
    BigDecimal averageBuyPrice,
    BigDecimal currentPrice,
    BigDecimal purchaseAmount,
    BigDecimal valuationAmount,
    BigDecimal profitAmount,
    BigDecimal profitRate,
    BigDecimal weightRate
) {
}
