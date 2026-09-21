package com.sagopalgo.api.market.dto;

import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.StockCandle;
import java.util.List;

/**
 * 선택된 Provider와 정규화된 캔들 목록을 함께 반환합니다.
 */
public record MarketCandleResponse(
    String provider,
    String stockCode,
    String market,
    CandleInterval interval,
    int count,
    List<StockCandle> candles
) {
}
