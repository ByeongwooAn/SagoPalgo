package com.sagopalgo.api.research.dto;

import com.sagopalgo.api.research.model.ResearchSyncStatusRecord;
import java.time.Instant;
import java.time.ZoneOffset;

/**
 * 한 종목의 마지막 뉴스·공시 동기화 결과입니다.
 */
public record ResearchSyncStatusItemResponse(
    String stockCode,
    String stockName,
    String triggerType,
    String status,
    int newsCount,
    int disclosureCount,
    int providerSuccessCount,
    int providerFailureCount,
    int providerDisabledCount,
    String message,
    Instant lastAttemptedAt,
    Instant lastSucceededAt
) {
    public static ResearchSyncStatusItemResponse from(ResearchSyncStatusRecord record) {
        return new ResearchSyncStatusItemResponse(
            record.getStockCode(),
            record.getStockName(),
            record.getTriggerType(),
            record.getStatus(),
            record.getNewsCount(),
            record.getDisclosureCount(),
            record.getProviderSuccessCount(),
            record.getProviderFailureCount(),
            record.getProviderDisabledCount(),
            record.getMessage(),
            record.getLastAttemptedAt().atOffset(ZoneOffset.UTC).toInstant(),
            record.getLastSucceededAt() == null
                ? null
                : record.getLastSucceededAt().atOffset(ZoneOffset.UTC).toInstant()
        );
    }
}
