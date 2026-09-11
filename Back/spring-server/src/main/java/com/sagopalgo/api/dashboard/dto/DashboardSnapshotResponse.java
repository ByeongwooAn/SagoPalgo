package com.sagopalgo.api.dashboard.dto;

import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.PortfolioSummaryResponse;
import java.util.List;

/**
 * 앱 홈/추천/보유/알림 탭을 한 번에 구성하기 위한 초기 스냅샷 DTO입니다.
 */
public record DashboardSnapshotResponse(
    DashboardMarketSummaryResponse marketSummary,
    DashboardRecommendationResponse recommendation,
    PortfolioSummaryResponse portfolioSummary,
    List<HoldingResponse> holdings,
    List<DashboardAlertResponse> alerts
) {
}
