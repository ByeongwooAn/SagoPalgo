package com.sagopalgo.api.market.dto;

import com.sagopalgo.api.market.model.StockQuote;
import java.math.BigDecimal;
import java.time.Instant;

public record MarketQuoteResponse(
    String provider, String stockCode, String market, String currency, BigDecimal currentPrice, Instant receivedAt
) {
    public static MarketQuoteResponse fromUsQuote(StockQuote quote) {
        return new MarketQuoteResponse(quote.provider(), quote.stockCode(), quote.market(), "USD",
            quote.currentPrice(), quote.receivedAt());
    }
}
