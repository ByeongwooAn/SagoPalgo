package com.sagopalgo.api.order.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import java.math.BigDecimal;

/**
 * 실제 주문 전에 안전 조건만 검증할 지정가 주문안입니다.
 */
public record OrderPrecheckRequest(
    @NotBlank(message = "종목 코드는 필수입니다.") String stockCode,
    @NotBlank(message = "종목명은 필수입니다.") String stockName,
    @NotBlank(message = "시장 코드는 필수입니다.") String market,
    @NotBlank(message = "주문 방향은 필수입니다.")
    @Pattern(regexp = "BUY|SELL", flags = Pattern.Flag.CASE_INSENSITIVE, message = "주문 방향은 BUY 또는 SELL이어야 합니다.")
    String side,
    @NotNull(message = "지정가는 필수입니다.")
    @DecimalMin(value = "0.01", message = "지정가는 0보다 커야 합니다.")
    @Digits(integer = 16, fraction = 2, message = "지정가는 소수점 2자리까지 입력할 수 있습니다.")
    BigDecimal limitPrice,
    @NotNull(message = "주문 수량은 필수입니다.")
    @DecimalMin(value = "0.0001", message = "주문 수량은 0보다 커야 합니다.")
    @Digits(integer = 14, fraction = 4, message = "주문 수량은 소수점 4자리까지 입력할 수 있습니다.")
    BigDecimal quantity
) {
}
