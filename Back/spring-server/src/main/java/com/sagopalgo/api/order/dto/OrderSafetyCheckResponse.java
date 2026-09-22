package com.sagopalgo.api.order.dto;

/**
 * 주문 사전검증의 개별 안전 조건 결과입니다.
 */
public record OrderSafetyCheckResponse(
    String code,
    String label,
    boolean passed,
    String message
) {
}
