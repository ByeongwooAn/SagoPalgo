package com.sagopalgo.api.order.model;

import java.time.LocalDateTime;

/** 주문 행이나 계좌 정보를 제외한 읽기 전용 점검 결과입니다. */
public record OrderReadOnlyProbeRecord(
    Long userId,
    String status,
    String orderDate,
    LocalDateTime checkedAt
) {
}
