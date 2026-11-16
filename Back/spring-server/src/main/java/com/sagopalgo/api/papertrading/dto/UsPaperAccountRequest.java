package com.sagopalgo.api.papertrading.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

public record UsPaperAccountRequest(
    @NotNull @DecimalMin("0.01") @Digits(integer = 16, fraction = 2)
    BigDecimal initialCapital
) {
}
