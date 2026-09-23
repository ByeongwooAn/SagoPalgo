package com.sagopalgo.api.order.model;

import java.time.LocalDate;
import java.time.LocalDateTime;

public class OrderReconciliationCheckRecord {
    private Long orderReconciliationCheckId;
    private Long orderApprovalId;
    private Long userId;
    private LocalDate orderDate;
    private String orderNo;
    private boolean completeScan;
    private int pagesScanned;
    private int matchCount;
    private String reviewStatus;
    private LocalDateTime checkedAt;

    public Long getOrderReconciliationCheckId() { return orderReconciliationCheckId; }
    public void setOrderReconciliationCheckId(Long value) { orderReconciliationCheckId = value; }
    public Long getOrderApprovalId() { return orderApprovalId; }
    public void setOrderApprovalId(Long value) { orderApprovalId = value; }
    public Long getUserId() { return userId; }
    public void setUserId(Long value) { userId = value; }
    public LocalDate getOrderDate() { return orderDate; }
    public void setOrderDate(LocalDate value) { orderDate = value; }
    public String getOrderNo() { return orderNo; }
    public void setOrderNo(String value) { orderNo = value; }
    public boolean isCompleteScan() { return completeScan; }
    public void setCompleteScan(boolean value) { completeScan = value; }
    public int getPagesScanned() { return pagesScanned; }
    public void setPagesScanned(int value) { pagesScanned = value; }
    public int getMatchCount() { return matchCount; }
    public void setMatchCount(int value) { matchCount = value; }
    public String getReviewStatus() { return reviewStatus; }
    public void setReviewStatus(String value) { reviewStatus = value; }
    public LocalDateTime getCheckedAt() { return checkedAt; }
    public void setCheckedAt(LocalDateTime value) { checkedAt = value; }
}
