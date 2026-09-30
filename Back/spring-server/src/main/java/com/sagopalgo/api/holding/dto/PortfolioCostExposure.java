package com.sagopalgo.api.holding.dto;

import java.math.BigDecimal;

/** 매입 원금 기준 비중이며 실시간 평가금액이나 KB 계좌 전체 비중이 아닙니다. */
public record PortfolioCostExposure(
    BigDecimal portfolioWeightRate,
    BigDecimal capitalWeightRate,
    BigDecimal maxCapitalWeightRate
) {
}
