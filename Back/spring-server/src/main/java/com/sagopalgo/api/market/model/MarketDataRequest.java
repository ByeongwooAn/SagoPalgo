package com.sagopalgo.api.market.model;

import com.sagopalgo.api.holding.model.Holding;

/**
 * 외부 시세 Provider에 전달하는 내부 표준 요청 모델입니다.
 */
public record MarketDataRequest(
    String stockCode,
    String market
) {

    public static MarketDataRequest from(Holding holding) {
        if (holding == null) {
            return new MarketDataRequest("", "");
        }
        return new MarketDataRequest(holding.getStockCode(), holding.getMarket());
    }
}
