package com.sagopalgo.api.research.service;

import com.sagopalgo.api.research.dto.ResearchSyncStatusItemResponse;
import com.sagopalgo.api.research.mapper.ResearchSyncStatusMapper;
import com.sagopalgo.api.research.model.ResearchSyncStatusRecord;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 종목별 마지막 뉴스·공시 동기화 상태를 영속화합니다.
 */
@Service
public class ResearchSyncStatusStore {

    private static final int MESSAGE_MAX_LENGTH = 500;

    private final ResearchSyncStatusMapper mapper;

    public ResearchSyncStatusStore(ResearchSyncStatusMapper mapper) {
        this.mapper = mapper;
    }

    @Transactional
    public void save(
        Long userId,
        String stockCode,
        String stockName,
        String triggerType,
        String status,
        int newsCount,
        int disclosureCount,
        int providerSuccessCount,
        int providerFailureCount,
        int providerDisabledCount,
        String message
    ) {
        LocalDateTime attemptedAt = LocalDateTime.now(ZoneOffset.UTC);
        ResearchSyncStatusRecord record = new ResearchSyncStatusRecord();
        record.setUserId(userId);
        record.setStockCode(stockCode);
        record.setStockName(stockName);
        record.setTriggerType(triggerType);
        record.setStatus(status);
        record.setNewsCount(newsCount);
        record.setDisclosureCount(disclosureCount);
        record.setProviderSuccessCount(providerSuccessCount);
        record.setProviderFailureCount(providerFailureCount);
        record.setProviderDisabledCount(providerDisabledCount);
        record.setMessage(limit(message));
        record.setLastAttemptedAt(attemptedAt);
        record.setLastSucceededAt(
            "SUCCESS".equals(status) || "PARTIAL".equals(status) ? attemptedAt : null
        );
        mapper.upsert(record);
    }

    @Transactional(readOnly = true)
    public Optional<ResearchSyncStatusItemResponse> find(Long userId, String stockCode) {
        return mapper.findByUserIdAndStockCode(userId, stockCode)
            .map(ResearchSyncStatusItemResponse::from);
    }

    private String limit(String value) {
        String normalized = value == null || value.isBlank() ? "동기화 결과 메시지가 없습니다." : value.trim();
        return normalized.length() <= MESSAGE_MAX_LENGTH
            ? normalized
            : normalized.substring(0, MESSAGE_MAX_LENGTH);
    }
}
