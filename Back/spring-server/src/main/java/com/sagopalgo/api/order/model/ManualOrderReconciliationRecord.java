package com.sagopalgo.api.order.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 사용자 확정과 조회된 체결 근거. 응답에는 계좌 지문을 제외합니다. */
public record ManualOrderReconciliationRecord(
    String commandId, Long userId, String accountFingerprint, String orderDate, String orderNo,
    String orderTime, BigDecimal filledQuantity, LocalDateTime confirmedAt
) {}
