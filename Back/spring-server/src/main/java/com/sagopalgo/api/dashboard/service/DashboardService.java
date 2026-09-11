package com.sagopalgo.api.dashboard.service;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.dashboard.dto.DashboardAlertResponse;
import com.sagopalgo.api.dashboard.dto.DashboardMarketSummaryResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationReasonResponse;
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

    private static final BigDecimal MONTHLY_RETURN_RATE = new BigDecimal("3.8");
    private static final int MARKET_SCORE = 76;
    private static final int POSITIVE_NEWS_COUNT = 12;

    private final CapitalService capitalService;
    private final HoldingService holdingService;

    public DashboardService(CapitalService capitalService, HoldingService holdingService) {
        this.capitalService = capitalService;
        this.holdingService = holdingService;
    }

    @Transactional(readOnly = true)
    public DashboardSnapshotResponse getSnapshot(Long userId) {
        CapitalResponse capital = capitalService.findByUserId(userId);
        HoldingsListResponse holdings = holdingService.findAll(userId);

        return new DashboardSnapshotResponse(
            marketSummary(capital),
            recommendation(holdings.items()),
            holdings.summary(),
            holdings.items(),
            alerts(holdings.items())
        );
    }

    private DashboardMarketSummaryResponse marketSummary(CapitalResponse capital) {
        return new DashboardMarketSummaryResponse(
            capital.availableCapital(),
            MONTHLY_RETURN_RATE,
            positionRange(capital.recommendedMinPosition(), capital.recommendedMaxPosition()),
            "강세",
            MARKET_SCORE,
            "긍정",
            POSITIVE_NEWS_COUNT,
            List.of(
                new BigDecimal("0.42"),
                new BigDecimal("0.68"),
                new BigDecimal("0.54"),
                new BigDecimal("0.82"),
                new BigDecimal("0.61"),
                new BigDecimal("0.94")
            )
        );
    }

    private DashboardRecommendationResponse recommendation(List<HoldingResponse> holdings) {
        HoldingResponse primaryHolding = holdings.isEmpty() ? null : holdings.get(0);
        String stockName = primaryHolding == null ? "삼성전자" : primaryHolding.stockName();
        String stockCode = primaryHolding == null ? "005930" : primaryHolding.stockCode();
        String market = primaryHolding == null ? "KOSPI" : primaryHolding.market();
        BigDecimal entryPrice = primaryHolding == null ? new BigDecimal("72000") : primaryHolding.currentPrice();

        return new DashboardRecommendationResponse(
            null,
            stockName,
            stockCode,
            market,
            "강한 매수",
            87,
            entryPrice.stripTrailingZeros(),
            new BigDecimal("-5").stripTrailingZeros(),
            "시장 강세와 거래량 증가가 동시에 나타나 단기 관심 종목으로 분류됩니다. 전체 자산의 1~2% 손실 제한을 유지하세요.",
            List.of(
                new DashboardRecommendationReasonResponse(
                    "RSI",
                    "과매도 구간에서 반등 신호가 확인되었습니다.",
                    "TECHNICAL",
                    20
                ),
                new DashboardRecommendationReasonResponse(
                    "MACD",
                    "골든크로스 초기 구간으로 추세 전환 가능성이 있습니다.",
                    "TREND",
                    20
                ),
                new DashboardRecommendationReasonResponse(
                    "뉴스",
                    "AI 반도체 수주 관련 긍정 감성이 증가했습니다.",
                    "NEWS",
                    15
                )
            )
        );
    }

    private List<DashboardAlertResponse> alerts(List<HoldingResponse> holdings) {
        String sellCandidate = holdings.isEmpty() ? "삼성전자" : holdings.get(0).stockName();

        return List.of(
            new DashboardAlertResponse(
                sellCandidate + " 매도 검토",
                "현재 수익률이 목표 구간에 가까워 부분 익절 여부를 확인해 보세요.",
                "방금 전",
                "SELL"
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
