package com.sagopalgo.api.papertrading.dto;

import java.util.List;

/**
 * 모의매매 탭에 필요한 성과, 보유 포지션, 거래 이력을 묶습니다.
 */
public record PaperTradingSnapshotResponse(
    PaperTradingSummaryResponse summary,
    List<PaperPositionResponse> positions,
    List<PaperTradeResponse> trades
) {
}
