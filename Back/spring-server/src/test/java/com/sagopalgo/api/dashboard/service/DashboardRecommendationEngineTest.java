package com.sagopalgo.api.dashboard.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

class DashboardRecommendationEngineTest {

    private final DashboardRecommendationEngine engine = new DashboardRecommendationEngine();

    @Test
    @DisplayName("보유 종목이 없으면 추천을 반환하지 않는다")
    void recommendsDefaultBuyCandidateWhenHoldingsAreEmpty() {
        DashboardRecommendationResponse response = engine.recommend(List.of());

        assertThat(response).isNull();
    }

    @Test
    @DisplayName("수익률이 익절 기준에 가까우면 부분 익절 검토를 반환한다")
    void recommendsPartialTakeProfitNearTakeProfitRate() {
        DashboardRecommendationResponse response = engine.recommend(List.of(
            holding("005930", "삼성전자", "8.4", "-5", "9")
        ));

        assertThat(response.status()).isEqualTo("부분 익절 검토");
        assertThat(response.score()).isEqualTo(82);
        assertThat(response.aiSummary()).contains("익절 기준");
    }

    @Test
    @DisplayName("수익률이 손절 기준에 가까우면 손절 감시를 반환한다")
    void recommendsStopLossWatchNearStopLossRate() {
        DashboardRecommendationResponse response = engine.recommend(List.of(
            holding("005380", "현대차", "-4.2", "-5", "9")
        ));

        assertThat(response.status()).isEqualTo("손절 감시");
        assertThat(response.score()).isEqualTo(36);
        assertThat(response.aiSummary()).contains("손실 제한");
    }

    private HoldingResponse holding(
        String stockCode,
        String stockName,
        String profitRate,
        String stopLossRate,
        String takeProfitRate
    ) {
        return new HoldingResponse(
            1L,
            stockCode,
            stockName,
            "KOSPI",
            new BigDecimal("70000"),
            new BigDecimal("10"),
            LocalDate.parse("2026-09-12"),
            new BigDecimal("76000"),
            new BigDecimal(profitRate),
            new BigDecimal(stopLossRate),
            new BigDecimal(takeProfitRate),
            "HOLDING",
            "보유"
        );
    }
}
