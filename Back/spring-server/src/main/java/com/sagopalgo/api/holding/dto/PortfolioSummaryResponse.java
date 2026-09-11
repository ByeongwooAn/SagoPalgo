package com.sagopalgo.api.holding.dto;

import java.math.BigDecimal;

/**
 * 보유 종목 화면 상단의 포트폴리오 요약 DTO입니다.
 */
public record PortfolioSummaryResponse(
    BigDecimal totalProfit,
    BigDecimal profitRate,
    BigDecimal maxAllowedLoss,
    BigDecimal riskUsageRate
) {
}
