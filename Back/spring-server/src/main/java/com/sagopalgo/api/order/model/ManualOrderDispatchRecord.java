package com.sagopalgo.api.order.model;

import com.sagopalgo.api.order.service.OrderDispatchReceipt;
import java.time.LocalDateTime;

/** executionKey는 내부 실행 소유권이며 API에 반환하지 않습니다. */
public record ManualOrderDispatchRecord(String commandId, Long userId, String executionKey, String phase,
    String outcomeStatus, String orderNo, String resultCode, String processCode,
    LocalDateTime reservedAt, LocalDateTime startedAt, LocalDateTime returnedAt) {
    public OrderDispatchReceipt receipt() {
        return "RETURNED".equals(phase) ? new OrderDispatchReceipt(outcomeStatus, orderNo, resultCode, processCode) : null;
    }
}
