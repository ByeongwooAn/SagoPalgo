package com.sagopalgo.api.dashboard.service;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.alert.service.AlertService;
import com.sagopalgo.api.dashboard.dto.DashboardMarketSummaryResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.dashboard.dto.DashboardSnapshotResponse;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 앱 초기 진입 화면에 필요한 여러 투자 데이터를 하나의 응답으로 조합합니다.
 */
@Service
public class DashboardService {

    private final CapitalService capitalService;
    private final HoldingService holdingService;
    private final DashboardRecommendationEngine recommendationEngine;
    private final RecommendationService recommendationService;
    private final AlertService alertService;

    public DashboardService(
        CapitalService capitalService,
        HoldingService holdingService,
        DashboardRecommendationEngine recommendationEngine,
        RecommendationService recommendationService,
        AlertService alertService
    ) {
        this.capitalService = capitalService;
        this.holdingService = holdingService;
        this.recommendationEngine = recommendationEngine;
        this.recommendationService = recommendationService;
        this.alertService = alertService;
    }

    @Transactional(readOnly = true)
    public DashboardSnapshotResponse getSnapshot(Long userId) {
        CapitalResponse capital = capitalService.findByUserId(userId);
        HoldingsListResponse holdings = holdingService.findAll(userId);
        DashboardRecommendationResponse recommendation = holdings.items().isEmpty()
            ? null
            : recommendationService.findLatestDashboardRecommendation(userId)
                .filter(stored -> holdings.items().stream().anyMatch(
                    holding -> holding.stockCode().equals(stored.stockCode())
                        && holding.market().equalsIgnoreCase(stored.market())
                ))
                .orElseGet(() -> recommendationEngine.recommend(holdings.items()));

        return new DashboardSnapshotResponse(
            marketSummary(capital, holdings),
            recommendation,
            holdings.summary(),
            holdings.items(),
            alertService.latestDashboardAlerts(userId)
        );
    }

    private DashboardMarketSummaryResponse marketSummary(CapitalResponse capital, HoldingsListResponse holdings) {
        return new DashboardMarketSummaryResponse(
            capital.availableCapital(),
            holdings.summary().profitRate(),
            positionRange(capital.recommendedMinPosition(), capital.recommendedMaxPosition()),
            "데이터 없음",
            0,
            "데이터 없음",
            0,
            List.of()
        );
    }

    private String positionRange(BigDecimal minPosition, BigDecimal maxPosition) {
        BigDecimal tenThousand = new BigDecimal("10000");
        if (minPosition.compareTo(tenThousand) >= 0 && maxPosition.compareTo(tenThousand) >= 0) {
            return formatManwonAmount(minPosition) + "~" + formatManwonAmount(maxPosition) + "만원";
        }

        return formatAmount(minPosition) + "~" + formatAmount(maxPosition);
    }

    private String formatAmount(BigDecimal value) {
        BigDecimal tenThousand = new BigDecimal("10000");
        if (value.compareTo(tenThousand) >= 0) {
            return formatManwonAmount(value) + "만원";
        }

        return value.setScale(0, RoundingMode.HALF_UP).toPlainString() + "원";
    }

    private String formatManwonAmount(BigDecimal value) {
        return value
            .divide(new BigDecimal("10000"), 1, RoundingMode.HALF_UP)
            .stripTrailingZeros()
            .toPlainString();
    }
}
