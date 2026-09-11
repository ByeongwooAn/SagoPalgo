package com.sagopalgo.api.dashboard.service;

import com.sagopalgo.api.dashboard.dto.DashboardRecommendationReasonResponse;
import com.sagopalgo.api.dashboard.dto.DashboardRecommendationResponse;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import org.springframework.stereotype.Component;

/**
 * Python AI 서버가 붙기 전까지 사용할 MVP 추천 엔진입니다.
 *
 * <p>현재는 실제 DB에 저장된 보유 종목의 수익률, 손절/익절 기준을 조합해 설명 가능한 대표 추천을
 * 만듭니다. 이후 AI 서버 응답 DTO를 이 클래스 입력으로 바꾸면 화면 계약은 그대로 유지할 수 있습니다.
 */
@Component
public class DashboardRecommendationEngine {

    public DashboardRecommendationResponse recommend(List<HoldingResponse> holdings) {
        if (holdings.isEmpty()) {
            return null;
        }

        HoldingResponse holding = selectPrimaryHolding(holdings);
        BigDecimal profitRate = holding.profitRate();
        if (profitRate.compareTo(holding.takeProfitRate().subtract(BigDecimal.ONE)) >= 0) {
            return takeProfitCandidate(holding);
        }

        if (profitRate.compareTo(holding.stopLossRate().add(BigDecimal.ONE)) <= 0) {
            return stopLossCandidate(holding);
        }

        return holdCandidate(holding);
    }

    private HoldingResponse selectPrimaryHolding(List<HoldingResponse> holdings) {
        return holdings.stream()
            .max(Comparator.comparing(holding -> holding.profitRate().abs()))
            .orElseThrow();
    }

    private DashboardRecommendationResponse takeProfitCandidate(HoldingResponse holding) {
        return new DashboardRecommendationResponse(
            holding.holdingId(),
            holding.stockName(),
            holding.stockCode(),
            holding.market(),
            "부분 익절 검토",
            82,
            holding.currentPrice().stripTrailingZeros(),
            holding.stopLossRate().stripTrailingZeros(),
            holding.stockName() + " 수익률이 익절 기준에 가까워졌습니다. 보유 수량 일부를 줄이고 남은 물량은 추세를 확인하세요.",
            List.of(
                new DashboardRecommendationReasonResponse(
                    "수익률",
                    "현재 수익률 " + holding.profitRate().stripTrailingZeros().toPlainString() + "%로 목표 수익 구간에 접근했습니다.",
                    "TREND",
                    25
                ),
                new DashboardRecommendationReasonResponse(
                    "리스크",
                    "수익 구간에서 손절 기준을 끌어올려 원금 훼손 가능성을 낮출 수 있습니다.",
                    "TECHNICAL",
                    18
                ),
                new DashboardRecommendationReasonResponse(
                    "분할매도",
                    "전량 매도보다 부분 익절 후 잔여 물량 추적이 MVP 리스크 원칙에 맞습니다.",
                    "NEWS",
                    12
                )
            )
        );
    }

    private DashboardRecommendationResponse stopLossCandidate(HoldingResponse holding) {
        return new DashboardRecommendationResponse(
            holding.holdingId(),
            holding.stockName(),
            holding.stockCode(),
            holding.market(),
            "손절 감시",
            36,
            holding.currentPrice().stripTrailingZeros(),
            holding.stopLossRate().stripTrailingZeros(),
            holding.stockName() + " 손실률이 손절 기준에 가까워졌습니다. 추가 매수보다 손실 제한 계획을 먼저 확인하세요.",
            List.of(
                new DashboardRecommendationReasonResponse(
                    "손실률",
                    "현재 수익률 " + holding.profitRate().stripTrailingZeros().toPlainString() + "%로 방어 기준에 근접했습니다.",
                    "TECHNICAL",
                    -20
                ),
                new DashboardRecommendationReasonResponse(
                    "자본보존",
                    "한 번의 거래 손실이 전체 자본금 허용 범위를 넘지 않도록 포지션 축소를 검토합니다.",
                    "TREND",
                    18
                ),
                new DashboardRecommendationReasonResponse(
                    "대기",
                    "반등 확인 전까지 신규 진입 신호보다 위험 관리 신호를 우선합니다.",
                    "NEWS",
                    10
                )
            )
        );
    }

    private DashboardRecommendationResponse holdCandidate(HoldingResponse holding) {
        return new DashboardRecommendationResponse(
            holding.holdingId(),
            holding.stockName(),
            holding.stockCode(),
            holding.market(),
            "보유 유지",
            68,
            holding.currentPrice().stripTrailingZeros(),
            holding.stopLossRate().stripTrailingZeros(),
            holding.stockName() + " 현재 수익률은 손절/익절 기준 사이에 있습니다. 신규 판단보다 기존 계획을 유지하며 알림 기준을 확인하세요.",
            List.of(
                new DashboardRecommendationReasonResponse(
                    "계획 유지",
                    "현재 수익률 " + holding.profitRate().stripTrailingZeros().toPlainString() + "%로 즉시 매도 기준은 아닙니다.",
                    "TREND",
                    18
                ),
                new DashboardRecommendationReasonResponse(
                    "손절 기준",
                    "손절 기준 " + holding.stopLossRate().stripTrailingZeros().toPlainString() + "%를 이탈하는지 계속 감시합니다.",
                    "TECHNICAL",
                    15
                ),
                new DashboardRecommendationReasonResponse(
                    "관찰",
                    "시장 흐름은 긍정적이지만 추가 매수는 다음 신호 확인 후 판단합니다.",
                    "NEWS",
                    12
                )
            )
        );
    }
}
