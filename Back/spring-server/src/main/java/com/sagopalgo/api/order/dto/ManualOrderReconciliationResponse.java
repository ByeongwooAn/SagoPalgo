package com.sagopalgo.api.order.dto;

import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record ManualOrderReconciliationResponse(
    String orderDate, String orderNo, String orderTime, BigDecimal filledQuantity, LocalDateTime confirmedAt
) {
    public static ManualOrderReconciliationResponse from(ManualOrderReconciliationRecord record) {
        return record == null ? null : new ManualOrderReconciliationResponse(record.orderDate(), record.orderNo(),
            record.orderTime(), record.filledQuantity(), record.confirmedAt());
    }
}
