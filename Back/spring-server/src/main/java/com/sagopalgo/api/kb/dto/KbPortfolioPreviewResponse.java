package com.sagopalgo.api.kb.dto;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

/** 저장하지 않고 KB 보유분과 앱 반영 대상을 비교합니다. */
public record KbPortfolioPreviewResponse(
    String previewToken,
    Instant expiresAt,
    Instant checkedAt,
    BigDecimal currentCapital,
    BigDecimal orderAvailableCash,
    List<Item> items,
    int retainedImportedCount
) {
    public record Item(String stockCode, String stockName, String market,
        BigDecimal quantity, BigDecimal averageBuyPrice, String action, String message) {}
}
