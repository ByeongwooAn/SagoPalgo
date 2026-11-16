package com.sagopalgo.api.market.model;

import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import java.util.Locale;

/**
 * 외부 시세 Provider에 전달하는 내부 표준 요청 모델입니다.
 */
public record MarketDataRequest(
    String stockCode,
    String market
) {
    public static MarketDataRequest forLookup(String stockCode, String market) {
        String normalizedMarket = market.trim().toUpperCase(Locale.ROOT);
        String symbol = stockCode.trim();
        if (UsStockExchange.fromMarket(normalizedMarket).isPresent()) {
            symbol = symbol.toUpperCase(Locale.ROOT);
            if (!UsStockExchange.isTicker(symbol)) {
                throw new ApiException(ErrorCode.VALIDATION_ERROR, "미국주식 티커 형식이 올바르지 않습니다.");
            }
        }
        return new MarketDataRequest(symbol, normalizedMarket);
    }


    public static MarketDataRequest from(Holding holding) {
        if (holding == null) {
            return new MarketDataRequest("", "");
        }
        return new MarketDataRequest(holding.getStockCode(), holding.getMarket());
    }
}
