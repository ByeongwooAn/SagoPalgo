package com.sagopalgo.api.holding.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 보유 종목 등록/수정 요청 DTO입니다.
 */
public record HoldingRequest(
    @NotBlank(message = "종목 코드는 필수입니다.")
    String stockCode,

    @NotBlank(message = "종목명은 필수입니다.")
    String stockName,

    @NotBlank(message = "시장은 필수입니다.")
    String market,

    @NotNull(message = "매수가는 필수입니다.")
    @DecimalMin(value = "0.01", message = "매수가는 0보다 커야 합니다.")
    BigDecimal buyPrice,

    @NotNull(message = "수량은 필수입니다.")
    @DecimalMin(value = "0.0001", message = "수량은 0보다 커야 합니다.")
    BigDecimal quantity,

    @NotNull(message = "매수일은 필수입니다.")
    LocalDate buyDate,

    @NotNull(message = "손절 기준 수익률은 필수입니다.")
    @DecimalMin(value = "-100.000", message = "손절 기준 수익률은 -100 이상이어야 합니다.")
    @DecimalMax(value = "0.000", message = "손절 기준 수익률은 0 이하이어야 합니다.")
    BigDecimal stopLossRate,

    @NotNull(message = "익절 기준 수익률은 필수입니다.")
    @DecimalMin(value = "0.000", message = "익절 기준 수익률은 0 이상이어야 합니다.")
    BigDecimal takeProfitRate
) {
}
