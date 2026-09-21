package com.sagopalgo.api.market.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 외부 Provider별 캔들 응답을 앱 내부에서 사용하는 표준 형태로 정규화한 모델입니다.
 */
public record StockCandle(
    String provider,
    String stockCode,
    String market,
    LocalDateTime dateTime,
    CandleInterval interval,
    BigDecimal openPrice,
    BigDecimal highPrice,
    BigDecimal lowPrice,
    BigDecimal closePrice,
    BigDecimal volume
) {
}
