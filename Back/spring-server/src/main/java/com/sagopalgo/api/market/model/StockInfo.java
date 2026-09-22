package com.sagopalgo.api.market.model;

import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 외부 Provider의 종목 기본 정보를 앱 내부 형식으로 정규화한 모델입니다.
 */
public record StockInfo(
    String provider,
    String stockCode,
    String stockName,
    String englishName,
    String market,
    String securityType,
    boolean commonShare,
    String status,
    String currency,
    LocalDate listedAt,
    LocalDate delistedAt,
    BigDecimal sharesOutstanding,
    boolean nxtSupported,
    boolean tradingSuspended
) {
}
