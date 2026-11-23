package com.sagopalgo.api.papertrading.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;

/**
 * 화면에 표시할 단일 모의매매 체결 기록입니다.
 */
public record PaperTradeResponse(
    Long tradeRecordId,
    Long recommendationId,
    String stockCode,
    String stockName,
    String market,
    String tradeType,
    BigDecimal tradePrice,
    BigDecimal quantity,
    BigDecimal tradeAmount,
    BigDecimal realizedProfit,
    LocalDateTime tradeDate,
    String memo,
    @JsonInclude(JsonInclude.Include.NON_NULL) String quoteProvider,
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime quoteMarketAt,
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime quoteReceivedAt,
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonFormat(shape = JsonFormat.Shape.STRING) LocalDate signalBasisDate,
    @JsonInclude(JsonInclude.Include.NON_NULL) String signalModelSha256,
    @JsonInclude(JsonInclude.Include.NON_NULL)
    @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime signalExpiresAt
) {
}
