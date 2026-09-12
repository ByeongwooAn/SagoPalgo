package com.sagopalgo.api.kb.dto;

import java.math.BigDecimal;

/**
 * KB증권 잔고 현황 조회의 계좌 요약 응답입니다.
 */
public record KbBalanceSummaryResponse(
    String basis,
    BigDecimal cashDeposit,
    BigDecimal withdrawalAvailableAmount,
    BigDecimal orderAvailableCash,
    BigDecimal netAssetValuationAmount,
    BigDecimal securitiesNetValuationAmount,
    BigDecimal totalPurchaseAmount,
    BigDecimal totalValuationAmount,
    BigDecimal totalProfitAmount,
    BigDecimal totalYieldRate,
    BigDecimal financingAmount,
    BigDecimal mortgageRatio,
    String totalDataCount
) {
}
