package com.sagopalgo.api.research.model;

import java.time.LocalDateTime;

/**
 * research_sync_status 테이블의 종목별 마지막 동기화 상태입니다.
 */
public class ResearchSyncStatusRecord {

    private Long syncStatusId;
    private Long userId;
    private String stockCode;
    private String stockName;
    private String triggerType;
    private String status;
    private Integer newsCount;
    private Integer disclosureCount;
    private Integer providerSuccessCount;
    private Integer providerFailureCount;
    private Integer providerDisabledCount;
    private String message;
    private LocalDateTime lastAttemptedAt;
    private LocalDateTime lastSucceededAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getSyncStatusId() { return syncStatusId; }
    public void setSyncStatusId(Long syncStatusId) { this.syncStatusId = syncStatusId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getStockCode() { return stockCode; }
    public void setStockCode(String stockCode) { this.stockCode = stockCode; }
    public String getStockName() { return stockName; }
    public void setStockName(String stockName) { this.stockName = stockName; }
    public String getTriggerType() { return triggerType; }
    public void setTriggerType(String triggerType) { this.triggerType = triggerType; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public Integer getNewsCount() { return newsCount; }
    public void setNewsCount(Integer newsCount) { this.newsCount = newsCount; }
    public Integer getDisclosureCount() { return disclosureCount; }
    public void setDisclosureCount(Integer disclosureCount) { this.disclosureCount = disclosureCount; }
    public Integer getProviderSuccessCount() { return providerSuccessCount; }
    public void setProviderSuccessCount(Integer providerSuccessCount) { this.providerSuccessCount = providerSuccessCount; }
    public Integer getProviderFailureCount() { return providerFailureCount; }
    public void setProviderFailureCount(Integer providerFailureCount) { this.providerFailureCount = providerFailureCount; }
    public Integer getProviderDisabledCount() { return providerDisabledCount; }
    public void setProviderDisabledCount(Integer providerDisabledCount) { this.providerDisabledCount = providerDisabledCount; }
    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }
    public LocalDateTime getLastAttemptedAt() { return lastAttemptedAt; }
    public void setLastAttemptedAt(LocalDateTime lastAttemptedAt) { this.lastAttemptedAt = lastAttemptedAt; }
    public LocalDateTime getLastSucceededAt() { return lastSucceededAt; }
    public void setLastSucceededAt(LocalDateTime lastSucceededAt) { this.lastSucceededAt = lastSucceededAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
