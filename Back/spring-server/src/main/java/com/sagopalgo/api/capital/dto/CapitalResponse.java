package com.sagopalgo.api.capital.dto;

import com.sagopalgo.api.capital.model.UserCapital;
import java.math.BigDecimal;

/**
 * 자본금 조회/수정 API가 내려주는 응답 DTO입니다.
 */
public record CapitalResponse(
    BigDecimal availableCapital,
    BigDecimal recommendedMinPosition,
    BigDecimal recommendedMaxPosition,
    BigDecimal riskPerTradeRate
) {

    public static CapitalResponse from(UserCapital capital) {
        return new CapitalResponse(
            capital.getAvailableCapital().stripTrailingZeros(),
            capital.getRecommendedMinPosition().stripTrailingZeros(),
            capital.getRecommendedMaxPosition().stripTrailingZeros(),
            capital.getRiskPerTradeRate().stripTrailingZeros()
        );
    }
}
