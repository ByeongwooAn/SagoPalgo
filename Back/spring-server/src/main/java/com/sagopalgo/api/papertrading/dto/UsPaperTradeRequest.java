package com.sagopalgo.api.papertrading.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;

public record UsPaperTradeRequest(
    @NotBlank String stockCode,
    @NotBlank String market,
    @NotNull Side side,
    @NotNull @DecimalMin("0.0001") @Digits(integer = 14, fraction = 4) BigDecimal quantity,
    @NotNull @Pattern(regexp = "[0-9a-f]{32}") String requestId
) {
    public enum Side { BUY, SELL }
}
