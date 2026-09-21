package com.sagopalgo.api.market.model;

import java.math.BigDecimal;
import java.time.Instant;

/**
 * 현재가, 등락률, 거래량처럼 Provider마다 필드명이 다른 값을 내부 표준 형태로 묶은 모델입니다.
 */
public record StockQuote(
    String provider,
    String stockCode,
    String stockName,
    String market,
    BigDecimal currentPrice,
    BigDecimal changePrice,
    BigDecimal changeRate,
    BigDecimal volume,
    BigDecimal openPrice,
    BigDecimal highPrice,
    BigDecimal lowPrice,
    BigDecimal previousClose,
    Instant receivedAt
) {
}
