package com.sagopalgo.api.papertrading.dto;

import java.math.BigDecimal;

/**
 * 모의매매 자산과 성과를 한눈에 보여주는 집계값입니다.
 */
public record PaperTradingSummaryResponse(
    BigDecimal initialCapital,
    BigDecimal cashBalance,
    BigDecimal openPositionValue,
    BigDecimal totalAsset,
    BigDecimal realizedProfit,
    BigDecimal unrealizedProfit,
    BigDecimal totalProfit,
    BigDecimal returnRate,
    long completedTrades,
    BigDecimal winRate,
    BigDecimal maxLoss,
    BigDecimal turnoverRate
) {
}
