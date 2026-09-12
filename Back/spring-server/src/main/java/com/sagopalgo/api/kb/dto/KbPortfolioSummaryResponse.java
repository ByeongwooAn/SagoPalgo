package com.sagopalgo.api.kb.dto;

import java.math.BigDecimal;

/**
 * KB증권 계좌의 평가금액, 손익률, 비중 계산에 필요한 요약 응답입니다.
 */
public record KbPortfolioSummaryResponse(
    BigDecimal totalPurchaseAmount,
    BigDecimal totalValuationAmount,
    BigDecimal totalProfitAmount,
    BigDecimal profitRate
) {
}
