package com.sagopalgo.api.kb.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Map;

public record KbPortfolioImportRequest(
    @NotBlank @Size(max = 64) String previewToken,
    @NotNull Instant expiresAt,
    @NotNull Boolean importCapital,
    @NotNull Boolean importHoldings,
    @NotNull @Size(max = 200) Map<String, String> markets,
    @NotNull @DecimalMin("-100") @DecimalMax("0") @Digits(integer = 3, fraction = 3) BigDecimal stopLossRate,
    @NotNull @DecimalMin("0") @DecimalMax("999.999") @Digits(integer = 3, fraction = 3) BigDecimal takeProfitRate
) {}
