package com.sagopalgo.api.order.dto;

import jakarta.validation.constraints.NotBlank;

public record OrderDateReconciliationRequest(@NotBlank String orderDate) {
}
