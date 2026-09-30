package com.sagopalgo.api.order.model;

import java.time.LocalDateTime;

public class OrderApprovalRecord {
    private Long orderApprovalId;
    private Long userId;
    private Long orderPrecheckId;
    private String tokenHash;
    private String accountFingerprint;
    private LocalDateTime expiresAt;
    private LocalDateTime createdAt;

    public Long getOrderApprovalId() { return orderApprovalId; }
    public void setOrderApprovalId(Long orderApprovalId) { this.orderApprovalId = orderApprovalId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public Long getOrderPrecheckId() { return orderPrecheckId; }
    public void setOrderPrecheckId(Long orderPrecheckId) { this.orderPrecheckId = orderPrecheckId; }
    public String getTokenHash() { return tokenHash; }
    public void setTokenHash(String tokenHash) { this.tokenHash = tokenHash; }
    public String getAccountFingerprint() { return accountFingerprint; }
    public void setAccountFingerprint(String accountFingerprint) { this.accountFingerprint = accountFingerprint; }
    public LocalDateTime getExpiresAt() { return expiresAt; }
    public void setExpiresAt(LocalDateTime expiresAt) { this.expiresAt = expiresAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
