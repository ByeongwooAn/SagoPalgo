package com.sagopalgo.api.order.dto;

import jakarta.validation.constraints.NotBlank;

public record OrderReconciliationReviewRequest(
    @NotBlank String orderDate,
    @NotBlank String orderNo
) {
}
