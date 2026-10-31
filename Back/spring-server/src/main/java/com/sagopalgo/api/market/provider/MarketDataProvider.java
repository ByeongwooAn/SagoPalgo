package com.sagopalgo.api.market.provider;

import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockInfo;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.model.DomesticStockIdentity;
import java.util.List;
import java.util.Optional;

/**
 * KB/KIS/Toss 등 외부 시세 공급자를 앱 내부 표준 모델로 연결하는 경계입니다.
 */
public interface MarketDataProvider {

    String providerCode();

    boolean supports(MarketDataRequest request);

    StockQuote quote(MarketDataRequest request);

    default Optional<StockInfo> stockInfo(MarketDataRequest request) {
        return Optional.empty();
    }

    default Optional<DomesticStockIdentity> domesticStockIdentity(String stockCode) {
        return Optional.empty();
    }

    default List<StockCandle> candles(MarketDataRequest request, CandleInterval interval, int count) {
        return List.of();
    }
}
