package com.sagopalgo.api.holding.dto;

import java.util.List;

/**
 * 보유 종목 목록 조회 응답 DTO입니다.
 */
public record HoldingsListResponse(
    PortfolioSummaryResponse summary,
    List<HoldingResponse> items
) {
}
