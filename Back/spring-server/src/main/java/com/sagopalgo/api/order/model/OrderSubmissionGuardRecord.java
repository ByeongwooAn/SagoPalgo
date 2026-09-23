package com.sagopalgo.api.order.model;

import java.time.LocalDateTime;

public class OrderSubmissionGuardRecord {
    private Long orderApprovalId;
    private Long userId;
    private String status;
    private LocalDateTime reservedAt;
    private LocalDateTime uncertainAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getOrderApprovalId() { return orderApprovalId; }
    public void setOrderApprovalId(Long orderApprovalId) { this.orderApprovalId = orderApprovalId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public LocalDateTime getReservedAt() { return reservedAt; }
    public void setReservedAt(LocalDateTime reservedAt) { this.reservedAt = reservedAt; }
    public LocalDateTime getUncertainAt() { return uncertainAt; }
    public void setUncertainAt(LocalDateTime uncertainAt) { this.uncertainAt = uncertainAt; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(LocalDateTime updatedAt) { this.updatedAt = updatedAt; }
}
