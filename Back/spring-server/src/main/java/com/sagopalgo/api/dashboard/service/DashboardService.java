package com.sagopalgo.api.dashboard.service;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.dashboard.dto.DashboardAlertResponse;
import com.sagopalgo.api.dashboard.dto.DashboardMarketSummaryResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.dashboard.dto.DashboardSnapshotResponse;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.service.HoldingService;
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

    public DashboardService(
        CapitalService capitalService,
        HoldingService holdingService,
        DashboardRecommendationEngine recommendationEngine
    ) {
        this.capitalService = capitalService;
        this.holdingService = holdingService;
        this.recommendationEngine = recommendationEngine;
    }

    @Transactional(readOnly = true)
    public DashboardSnapshotResponse getSnapshot(Long userId) {
        CapitalResponse capital = capitalService.findByUserId(userId);
        HoldingsListResponse holdings = holdingService.findAll(userId);
        DashboardRecommendationResponse recommendation = recommendationEngine.recommend(holdings.items());

        return new DashboardSnapshotResponse(
            marketSummary(capital, holdings),
            recommendation,
            holdings.summary(),
            holdings.items(),
            alerts(recommendation)
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

    private List<DashboardAlertResponse> alerts(DashboardRecommendationResponse recommendation) {
        if (recommendation == null) {
            return List.of();
        }

        return List.of(
            new DashboardAlertResponse(
                recommendation.stockName() + " " + recommendation.status(),
                recommendation.aiSummary(),
                "방금 전",
                alertType(recommendation.status())
            ),
            new DashboardAlertResponse(
                "관심 종목 신규 후보",
                "RSI 과매도 탈출과 거래량 증가가 동시에 감지되었습니다.",
                "3분 전",
                "CANDIDATE"
            ),
            new DashboardAlertResponse(
                "시장 흐름 업데이트",
                "코스피와 나스닥 지표가 모두 강세 구간으로 전환되었습니다.",
                "5분 전",
                "MARKET"
            )
        );
    }

    private String alertType(String recommendationStatus) {
        if (recommendationStatus.contains("손절")) {
            return "RISK";
        }
        if (recommendationStatus.contains("익절")) {
            return "SELL";
        }
        return "CANDIDATE";
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
