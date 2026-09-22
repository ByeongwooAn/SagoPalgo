package com.sagopalgo.api.papertrading.dto;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.math.BigDecimal;

/**
 * 보유 중인 가상 포지션을 현재가로 매도하는 요청입니다.
 */
public record PaperSellRequest(
    @NotBlank(message = "종목 코드는 필수입니다.") String stockCode,
    @NotBlank(message = "시장 코드는 필수입니다.") String market,
    @NotNull(message = "가상 매도 수량은 필수입니다.")
    @DecimalMin(value = "0.0001", message = "가상 매도 수량은 0보다 커야 합니다.")
    @Digits(integer = 14, fraction = 4, message = "가상 매도 수량은 소수점 4자리까지 입력할 수 있습니다.")
    BigDecimal quantity
) {
}
