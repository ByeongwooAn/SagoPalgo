package com.sagopalgo.api.dashboard.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.alert.service.AlertService;
import com.sagopalgo.api.dashboard.dto.DashboardSnapshotResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.dashboard.dto.DashboardNewsSummary;
import com.sagopalgo.api.market.model.MarketIndexSnapshot;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.dto.PortfolioSummaryResponse;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * DashboardService가 여러 도메인 응답을 프론트 초기 스냅샷 계약으로 조합하는지 검증합니다.
 */
@ExtendWith(MockitoExtension.class)
class DashboardServiceTest {

    @Mock
    private CapitalService capitalService;

    @Mock
    private HoldingService holdingService;

    @Mock
    private RecommendationService recommendationService;

    @Mock
    private AlertService alertService;

    private DashboardService dashboardService;
    @Mock
    private DashboardBriefingService briefing;

    @BeforeEach
    void setUp() {
        when(briefing.index()).thenReturn(new MarketIndexSnapshot("DISABLED", "KIS", "설정 필요", null, null, null, List.of()));
        when(briefing.news(org.mockito.ArgumentMatchers.any())).thenReturn(new DashboardNewsSummary("EMPTY", "저장 뉴스 없음", "키워드 분류", 0, 0, 0, null));
        dashboardService = new DashboardService(
            capitalService,
            holdingService,
            briefing,
            recommendationService,
            alertService
        );
    }

    @Test
    @DisplayName("대시보드 스냅샷은 자본금과 보유 종목 요약을 한 응답으로 묶는다")
    void getSnapshotCombinesCapitalAndHoldings() {
        long userId = 1L;
        HoldingResponse holding = holding("005930", "삼성전자", "KOSPI", "69100");
        PortfolioSummaryResponse summary = new PortfolioSummaryResponse(
            new BigDecimal("128400"),
            new BigDecimal("4.2"),
            new BigDecimal("60000"),
            new BigDecimal("0.42")
        );

        when(capitalService.findByUserId(userId)).thenReturn(new CapitalResponse(
            new BigDecimal("3000000"),
            new BigDecimal("300000"),
            new BigDecimal("600000"),
            new BigDecimal("0.02")
        ));
        when(holdingService.findAll(userId)).thenReturn(new HoldingsListResponse(summary, List.of(holding)));

        DashboardSnapshotResponse response = dashboardService.getSnapshot(userId);

        assertThat(response.marketSummary().availableCapital()).isEqualByComparingTo("3000000");
        assertThat(response.marketSummary().recommendedPositionRange()).isEqualTo("30~60만원");
        assertThat(response.marketSummary().monthlyReturnRate()).isEqualByComparingTo("4.2");
        assertThat(response.marketSummary().portfolioReturnRate()).isEqualByComparingTo("4.2");
        assertThat(response.marketSummary().marketTrend()).isEqualTo("연동 설정 필요");
        assertThat(response.recommendation()).isNull();
        assertThat(response.portfolioSummary()).isSameAs(summary);
        assertThat(response.holdings()).containsExactly(holding);
        assertThat(response.alerts()).isEmpty();
    }

    @Test
    @DisplayName("보유 종목이 없으면 추천과 알림 없이 실제 빈 스냅샷을 반환한다")
    void getSnapshotReturnsDefaultRecommendationWhenHoldingsAreEmpty() {
        long userId = 2L;
        PortfolioSummaryResponse summary = new PortfolioSummaryResponse(
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO
        );

        when(capitalService.findByUserId(userId)).thenReturn(new CapitalResponse(
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            new BigDecimal("0.02")
        ));
        when(holdingService.findAll(userId)).thenReturn(new HoldingsListResponse(summary, List.of()));

        DashboardSnapshotResponse response = dashboardService.getSnapshot(userId);

        assertThat(response.marketSummary().recommendedPositionRange()).isEqualTo("0원~0원");
        assertThat(response.recommendation()).isNull();
        assertThat(response.holdings()).isEmpty();
        assertThat(response.alerts()).isEmpty();
    }

    @Test
    @DisplayName("현재 보유 종목의 저장 추천이 있으면 규칙 추천보다 우선한다")
    void getSnapshotUsesLatestStoredRecommendation() {
        long userId = 3L;
        HoldingResponse holding = holding("005930", "삼성전자", "KOSPI", "75200");
        PortfolioSummaryResponse summary = new PortfolioSummaryResponse(
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO
        );
        DashboardRecommendationResponse stored = new DashboardRecommendationResponse(
            99L,
            "삼성전자",
            "005930",
            "KOSPI",
            "매수 관찰",
            67,
            new BigDecimal("75200"),
            new BigDecimal("-5"),
            "저장된 통합 분석 결과입니다.",
            List.of()
        );
        when(capitalService.findByUserId(userId)).thenReturn(new CapitalResponse(
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            new BigDecimal("0.02")
        ));
        when(holdingService.findAll(userId)).thenReturn(new HoldingsListResponse(summary, List.of(holding)));
        when(recommendationService.findLatestDashboardRecommendation(userId)).thenReturn(Optional.of(stored));

        DashboardSnapshotResponse response = dashboardService.getSnapshot(userId);

        assertThat(response.recommendation()).isSameAs(stored);
        assertThat(response.recommendation().recommendationId()).isEqualTo(99L);
    }

    @Test
    void watchlistHeadlineWorksWithoutHoldingsAndIndexBarsUseActualOrderedCloses() {
        when(capitalService.findByUserId(4L)).thenReturn(new CapitalResponse(BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, new BigDecimal("0.02")));
        when(holdingService.findAll(4L)).thenReturn(new HoldingsListResponse(new PortfolioSummaryResponse(
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO), List.of()));
        var saved = new DashboardRecommendationResponse(25L, "관심 종목", "005930", "KOSPI", "매수 관찰", 65,
            new BigDecimal("100"), null, "저장 분석", List.of(), "BUY", "WATCHLIST", "BUY_WATCH",
            java.time.LocalDateTime.of(2026, 10, 31, 10, 0), null);
        when(recommendationService.findLatestDashboardRecommendation(4L)).thenReturn(Optional.of(saved));
        when(briefing.index()).thenReturn(new MarketIndexSnapshot("SUCCESS", "KIS", "KOSPI", new BigDecimal("3100"),
            new BigDecimal("1.25"), java.time.Instant.now(), List.of(
                new MarketIndexSnapshot.Point(LocalDate.of(2026, 10, 29), new BigDecimal("3000")),
                new MarketIndexSnapshot.Point(LocalDate.of(2026, 10, 30), new BigDecimal("3100")))));
        var response = dashboardService.getSnapshot(4L);
        assertThat(response.recommendation()).isSameAs(saved);
        assertThat(response.recommendation().analysisContext()).isEqualTo("WATCHLIST");
        assertThat(response.marketSummary().marketTrend()).isEqualTo("상승");
        assertThat(response.marketSummary().marketBars().get(0)).isEqualByComparingTo("0.15");
        assertThat(response.marketSummary().marketBars().get(1)).isEqualByComparingTo("1");
        assertThat(response.marketSummary().checkedAt()).isNotNull();
    }

    private HoldingResponse holding(String stockCode, String stockName, String market, String currentPrice) {
        return new HoldingResponse(
            21L,
            stockCode,
            stockName,
            market,
            new BigDecimal("69100"),
            new BigDecimal("12"),
            LocalDate.parse("2026-09-12"),
            new BigDecimal(currentPrice),
            new BigDecimal("0"),
            new BigDecimal("-5"),
            new BigDecimal("9"),
            "HOLDING",
            "보유"
        );
    }
}
