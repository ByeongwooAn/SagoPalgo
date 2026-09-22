package com.sagopalgo.api.watchlist.dto;

import com.sagopalgo.api.watchlist.model.WatchlistItem;
import com.sagopalgo.api.market.model.StockQuote;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.ZoneOffset;

/**
 * 관심 종목 목록 조회 응답의 단일 항목 DTO입니다.
 */
public record WatchlistResponse(
    Long watchlistId,
    String stockCode,
    String stockName,
    String market,
    Boolean alertEnabled,
    String provider,
    BigDecimal currentPrice,
    BigDecimal changeRate,
    Instant createdAt
) {

    public static WatchlistResponse from(WatchlistItem item, StockQuote quote) {
        return new WatchlistResponse(
            item.getWatchlistId(),
            item.getStockCode(),
            item.getStockName(),
            item.getMarket(),
            item.getAlertEnabled(),
            quote.provider(),
            quote.currentPrice(),
            quote.changeRate(),
            item.getCreatedAt().atOffset(ZoneOffset.UTC).toInstant()
        );
    }
}
