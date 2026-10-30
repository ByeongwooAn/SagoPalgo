package com.sagopalgo.api.holding.dto;

import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.Instant;
import com.sagopalgo.api.market.model.StockQuote;

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
    LocalDate buyDate,
    BigDecimal currentPrice,
    BigDecimal profitRate,
    BigDecimal stopLossRate,
    BigDecimal takeProfitRate,
    String status,
    String statusLabel,
    String priceProvider,
    Instant priceReceivedAt,
    boolean priceFallback,
    String source,
    LocalDateTime sourceSyncedAt
) {

    public HoldingResponse(Long holdingId, String stockCode, String stockName, String market,
        BigDecimal buyPrice, BigDecimal quantity, LocalDate buyDate, BigDecimal currentPrice,
        BigDecimal profitRate, BigDecimal stopLossRate, BigDecimal takeProfitRate, String status, String statusLabel) {
        this(holdingId, stockCode, stockName, market, buyPrice, quantity, buyDate, currentPrice,
            profitRate, stopLossRate, takeProfitRate, status, statusLabel, null, null, false, "MANUAL", null);
    }

    public static HoldingResponse from(Holding holding, StockQuote quote, BigDecimal profitRate) {
        HoldingResponse item = from(holding, quote.currentPrice(), profitRate);
        return new HoldingResponse(item.holdingId(), item.stockCode(), item.stockName(), item.market(),
            item.buyPrice(), item.quantity(), item.buyDate(), item.currentPrice(), item.profitRate(),
            item.stopLossRate(), item.takeProfitRate(), item.status(), item.statusLabel(),
            quote.provider(), "FALLBACK".equals(quote.provider()) ? null : quote.receivedAt(),
            "FALLBACK".equals(quote.provider()), holding.getSource(), holding.getSourceSyncedAt());
    }

    public static HoldingResponse from(Holding holding, BigDecimal currentPrice, BigDecimal profitRate) {
        return new HoldingResponse(
            holding.getHoldingId(),
            holding.getStockCode(),
            holding.getStockName(),
            holding.getMarket(),
            holding.getBuyPrice().stripTrailingZeros(),
            holding.getQuantity().stripTrailingZeros(),
            holding.getBuyDate(),
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
