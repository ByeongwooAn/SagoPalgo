package com.sagopalgo.api.kb.dto;

import java.util.List;

/**
 * KB증권 보유 주식 목록과 계좌 요약 응답입니다.
 */
public record KbHoldingsResponse(
    KbPortfolioSummaryResponse summary,
    List<KbHoldingResponse> items
) {
}
