package com.sagopalgo.api.order.dto;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderApprovalConfirmRequest(
    @NotNull Long approvalId,
    @NotBlank String token,
    @AssertTrue(message = "실주문이 아니라 승인 기록만 저장됨을 확인해야 합니다.") boolean acknowledged
) {
}
