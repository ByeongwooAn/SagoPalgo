package com.sagopalgo.api.papertrading.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;

/**
 * AI 추천을 기준으로 가상 매수할 수량입니다.
 */
public record PaperBuyRequest(
    @NotNull(message = "가상 매수 수량은 필수입니다.")
    @DecimalMin(value = "0.0001", message = "가상 매수 수량은 0보다 커야 합니다.")
    @Digits(integer = 14, fraction = 4, message = "가상 매수 수량은 소수점 4자리까지 입력할 수 있습니다.")
    BigDecimal quantity,
    @NotNull @Pattern(regexp = "[0-9a-f]{32}") String requestId
) {
}
