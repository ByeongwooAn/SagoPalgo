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
    private final DashboardBriefingService briefing;
    private final RecommendationService recommendationService;
    private final AlertService alertService;

    public DashboardService(
        CapitalService capitalService,
        HoldingService holdingService,
        DashboardBriefingService briefing,
        RecommendationService recommendationService,
        AlertService alertService
    ) {
        this.capitalService = capitalService;
        this.holdingService = holdingService;
        this.briefing = briefing;
        this.recommendationService = recommendationService;
        this.alertService = alertService;
    }

    @Transactional(readOnly = true)
    public DashboardSnapshotResponse getSnapshot(Long userId) {
        CapitalResponse capital = capitalService.findByUserId(userId);
        HoldingsListResponse holdings = holdingService.findAll(userId);
        // 보유/관심 등록 상태에 맞는 저장 분석만 표시합니다. GET에서 가짜 AI 결과를 생성하지 않습니다.
        DashboardRecommendationResponse recommendation = recommendationService.findLatestDashboardRecommendation(userId).orElse(null);

        return new DashboardSnapshotResponse(
            marketSummary(userId, capital, holdings),
            recommendation,
            holdings.summary(),
            holdings.items(),
            alertService.latestDashboardAlerts(userId)
        );
    }

    private DashboardMarketSummaryResponse marketSummary(Long userId, CapitalResponse capital, HoldingsListResponse holdings) {
        var index = briefing.index();
        var news = briefing.news(userId);
        boolean valid = "SUCCESS".equals(index.status());
        String trend = valid ? (index.changeRate().signum() > 0 ? "상승" : index.changeRate().signum() < 0 ? "하락" : "보합")
            : "DISABLED".equals(index.status()) ? "연동 설정 필요" : "조회 실패";
        List<BigDecimal> bars = List.of();
        if (valid && !index.points().isEmpty()) {
            var closes = index.points().stream().map(point -> point.close()).toList();
            BigDecimal min = closes.stream().min(BigDecimal::compareTo).orElseThrow();
            BigDecimal max = closes.stream().max(BigDecimal::compareTo).orElseThrow();
            bars = closes.stream().map(close -> max.compareTo(min) == 0 ? new BigDecimal("0.5") :
                close.subtract(min).divide(max.subtract(min), 6, RoundingMode.HALF_UP)
                    .multiply(new BigDecimal("0.85")).add(new BigDecimal("0.15"))).toList();
        }
        return new DashboardMarketSummaryResponse(
            capital.availableCapital(),
            holdings.summary().profitRate(), // 이전 앱용 숫자 별칭. 새 UI는 portfolioReturnRate를 '평가'로 표시합니다.
            positionRange(capital.recommendedMinPosition(), capital.recommendedMaxPosition()),
            trend,
            0,
            news.label(),
            news.positiveCount(),
            bars,
            holdings.summary().profitRate(),
            java.time.Instant.now(), index, news
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
