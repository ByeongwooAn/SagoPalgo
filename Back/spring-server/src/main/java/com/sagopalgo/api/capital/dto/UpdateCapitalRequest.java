package com.sagopalgo.api.capital.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

/**
 * 자본금 수정 API 요청 DTO입니다.
 */
public record UpdateCapitalRequest(
    @NotNull(message = "투자 가능 자본금은 필수입니다.")
    @DecimalMin(value = "0", message = "투자 가능 자본금은 0 이상이어야 합니다.")
    BigDecimal availableCapital,

    @NotNull(message = "1회 거래 리스크 비율은 필수입니다.")
    @DecimalMin(value = "0.0001", message = "1회 거래 리스크 비율은 0보다 커야 합니다.")
    @DecimalMax(value = "1.0000", message = "1회 거래 리스크 비율은 1 이하이어야 합니다.")
    BigDecimal riskPerTradeRate
) {
}
