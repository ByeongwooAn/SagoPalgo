package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;

public record ManualOrderObservation(String commandId, String status, boolean completeScan,
    BigDecimal filledQuantity, BigDecimal openQuantity, LocalDateTime checkedAt) {}
