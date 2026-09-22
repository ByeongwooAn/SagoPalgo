package com.sagopalgo.api.order.dto;

import java.util.List;

/**
 * 최근 주문 사전검증 감사 로그 목록입니다.
 */
public record OrderPrecheckHistoryResponse(
    List<OrderPrecheckHistoryItemResponse> items
) {
}
