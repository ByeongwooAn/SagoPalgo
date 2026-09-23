package com.sagopalgo.api.order.model;

import java.time.LocalDate;
import java.time.LocalDateTime;

public class OrderDateReconciliationCheckRecord {
    private Long orderDateReconciliationCheckId;
    private Long orderApprovalId;
    private Long userId;
    private LocalDate orderDate;
    private boolean completeScan;
    private int pagesScanned;
    private int rowCount;
    private boolean itemLimitReached;
    private LocalDateTime checkedAt;

    public Long getOrderDateReconciliationCheckId() { return orderDateReconciliationCheckId; }
    public void setOrderDateReconciliationCheckId(Long value) { orderDateReconciliationCheckId = value; }
    public Long getOrderApprovalId() { return orderApprovalId; }
    public void setOrderApprovalId(Long value) { orderApprovalId = value; }
    public Long getUserId() { return userId; }
    public void setUserId(Long value) { userId = value; }
    public LocalDate getOrderDate() { return orderDate; }
    public void setOrderDate(LocalDate value) { orderDate = value; }
    public boolean isCompleteScan() { return completeScan; }
    public void setCompleteScan(boolean value) { completeScan = value; }
    public int getPagesScanned() { return pagesScanned; }
    public void setPagesScanned(int value) { pagesScanned = value; }
    public int getRowCount() { return rowCount; }
    public void setRowCount(int value) { rowCount = value; }
    public boolean isItemLimitReached() { return itemLimitReached; }
    public void setItemLimitReached(boolean value) { itemLimitReached = value; }
    public LocalDateTime getCheckedAt() { return checkedAt; }
    public void setCheckedAt(LocalDateTime value) { checkedAt = value; }
}
