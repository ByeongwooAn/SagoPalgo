package com.sagopalgo.api.kb.dto;

import java.util.List;

/**
 * KB증권 잔고 현황 조회 응답입니다.
 */
public record KbBalanceResponse(
    KbBalanceSummaryResponse summary,
    List<KbBalanceItemResponse> items
) {
}
