package com.sagopalgo.api.dashboard.dto;

import java.math.BigDecimal;
import java.util.List;

/**
 * 홈 대시보드 상단 시장/자본금 요약 DTO입니다.
 */
public record DashboardMarketSummaryResponse(
    BigDecimal availableCapital,
    BigDecimal monthlyReturnRate,
    String recommendedPositionRange,
    String marketTrend,
    int marketScore,
    String newsSentiment,
    int positiveNewsCount,
    List<BigDecimal> marketBars
) {
}
