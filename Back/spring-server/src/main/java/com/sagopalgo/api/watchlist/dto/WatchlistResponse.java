package com.sagopalgo.api.watchlist.dto;

import com.sagopalgo.api.watchlist.model.WatchlistItem;
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
    Instant createdAt
) {

    public static WatchlistResponse from(WatchlistItem item) {
        return new WatchlistResponse(
            item.getWatchlistId(),
            item.getStockCode(),
            item.getStockName(),
            item.getMarket(),
            item.getAlertEnabled(),
            item.getCreatedAt().atOffset(ZoneOffset.UTC).toInstant()
        );
    }
}
