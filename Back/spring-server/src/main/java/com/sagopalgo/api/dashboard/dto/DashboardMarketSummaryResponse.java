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
    List<BigDecimal> marketBars,
    BigDecimal portfolioReturnRate,
    java.time.Instant checkedAt,
    com.sagopalgo.api.market.model.MarketIndexSnapshot index,
    DashboardNewsSummary news
) {
    public DashboardMarketSummaryResponse(BigDecimal capital, BigDecimal rate, String range, String trend,
        int score, String sentiment, int positive, List<BigDecimal> bars) {
        this(capital, rate, range, trend, score, sentiment, positive, bars, rate, null, null, null);
    }
}
