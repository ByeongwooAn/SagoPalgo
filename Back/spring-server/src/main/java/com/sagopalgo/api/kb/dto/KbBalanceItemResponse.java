package com.sagopalgo.api.kb.dto;

import java.math.BigDecimal;

/**
 * KB증권 잔고 현황 조회의 종목별 상세 응답입니다.
 */
public record KbBalanceItemResponse(
    String classification,
    String productType,
    String currencyCode,
    String stockCode,
    String stockName,
    BigDecimal quantity,
    BigDecimal orderableQuantity,
    BigDecimal unsettledSellQuantity,
    BigDecimal unsettledBuyQuantity,
    BigDecimal settlementQuantity,
    BigDecimal currentPrice,
    BigDecimal averageBuyPrice,
    BigDecimal purchaseAmount,
    BigDecimal valuationAmount,
    BigDecimal profitAmount,
    BigDecimal profitRate,
    BigDecimal valuationWeightRate,
    String detailTypeCode,
    String finalExecutionExchangeCode
) {
}
