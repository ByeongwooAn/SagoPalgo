package com.sagopalgo.api.holding.dto;

import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;

/**
 * 보유 종목 목록과 수정 응답의 단일 항목 DTO입니다.
 */
public record HoldingResponse(
    Long holdingId,
    String stockCode,
    String stockName,
    String market,
    BigDecimal buyPrice,
    BigDecimal quantity,
    BigDecimal currentPrice,
    BigDecimal profitRate,
    BigDecimal stopLossRate,
    BigDecimal takeProfitRate,
    String status,
    String statusLabel
) {

    public static HoldingResponse from(Holding holding, BigDecimal currentPrice, BigDecimal profitRate) {
        return new HoldingResponse(
            holding.getHoldingId(),
            holding.getStockCode(),
            holding.getStockName(),
            holding.getMarket(),
            holding.getBuyPrice().stripTrailingZeros(),
            holding.getQuantity().stripTrailingZeros(),
            currentPrice.stripTrailingZeros(),
            profitRate.stripTrailingZeros(),
            holding.getStopLossRate().stripTrailingZeros(),
            holding.getTakeProfitRate().stripTrailingZeros(),
            holding.getStatus(),
            statusLabel(holding.getStatus())
        );
    }

    private static String statusLabel(String status) {
        return switch (status) {
            case "PARTIAL_TAKE_PROFIT" -> "부분 익절";
            case "STOP_LOSS_WATCH" -> "손절 감시";
            case "SOLD" -> "매도 완료";
            default -> "보유";
        };
    }
}
