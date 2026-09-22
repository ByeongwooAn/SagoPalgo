package com.sagopalgo.api.market.dto;

import com.sagopalgo.api.market.model.StockInfo;
import java.math.BigDecimal;
import java.time.LocalDate;

/**
 * 종목 기본 정보 Provider 결과를 Flutter에 전달하는 응답입니다.
 */
public record MarketStockInfoResponse(
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

    public static MarketStockInfoResponse from(StockInfo info) {
        return new MarketStockInfoResponse(
            info.provider(),
            info.stockCode(),
            info.stockName(),
            info.englishName(),
            info.market(),
            info.securityType(),
            info.commonShare(),
            info.status(),
            info.currency(),
            info.listedAt(),
            info.delistedAt(),
            info.sharesOutstanding(),
            info.nxtSupported(),
            info.tradingSuspended()
        );
    }
}
