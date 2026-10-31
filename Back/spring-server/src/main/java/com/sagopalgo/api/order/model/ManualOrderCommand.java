package com.sagopalgo.api.order.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 불변 주문안과 단일 전송의 감사 기록. 비밀값은 응답 DTO에 포함하지 않습니다. */
public record ManualOrderCommand(
    String commandId, Long userId, Long approvalId, String parentId, String kind,
    String stockCode, String stockName, String market, String side, BigDecimal price, BigDecimal quantity,
    String accountFingerprint, String tokenHash, LocalDateTime expiresAt, String status,
    String orderNo, String orderDate, String resultCode, String processCode, String changeId,
    LocalDateTime createdAt, LocalDateTime updatedAt
) {}
