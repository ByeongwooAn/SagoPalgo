package com.sagopalgo.api.holding.model;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

/**
 * holdings 테이블의 한 행을 표현하는 모델입니다.
 */
public class Holding {

    private Long holdingId;
    private Long userId;
    private String stockCode;
    private String stockName;
    private String market;
    private BigDecimal buyPrice;
    private BigDecimal quantity;
    private LocalDate buyDate;
    private BigDecimal stopLossRate;
    private BigDecimal takeProfitRate;
    private String status;
    private String source = "MANUAL";
    private String sourceAccountKey;
    private LocalDateTime sourceSyncedAt;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getHoldingId() {
        return holdingId;
    }

    public String getSource() { return source; }
    public void setSource(String source) { this.source = source; }
    public String getSourceAccountKey() { return sourceAccountKey; }
    public void setSourceAccountKey(String key) { this.sourceAccountKey = key; }
    public LocalDateTime getSourceSyncedAt() { return sourceSyncedAt; }
    public void setSourceSyncedAt(LocalDateTime at) { this.sourceSyncedAt = at; }

    public void setHoldingId(Long holdingId) {
        this.holdingId = holdingId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public String getStockCode() {
        return stockCode;
    }

    public void setStockCode(String stockCode) {
        this.stockCode = stockCode;
    }

    public String getStockName() {
        return stockName;
    }

    public void setStockName(String stockName) {
        this.stockName = stockName;
    }

    public String getMarket() {
        return market;
    }

    public void setMarket(String market) {
        this.market = market;
    }

    public BigDecimal getBuyPrice() {
        return buyPrice;
    }

    public void setBuyPrice(BigDecimal buyPrice) {
        this.buyPrice = buyPrice;
    }

    public BigDecimal getQuantity() {
        return quantity;
    }

    public void setQuantity(BigDecimal quantity) {
        this.quantity = quantity;
    }

    public LocalDate getBuyDate() {
        return buyDate;
    }

    public void setBuyDate(LocalDate buyDate) {
        this.buyDate = buyDate;
    }

    public BigDecimal getStopLossRate() {
        return stopLossRate;
    }

    public void setStopLossRate(BigDecimal stopLossRate) {
        this.stopLossRate = stopLossRate;
    }

    public BigDecimal getTakeProfitRate() {
        return takeProfitRate;
    }

    public void setTakeProfitRate(BigDecimal takeProfitRate) {
        this.takeProfitRate = takeProfitRate;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public void setCreatedAt(LocalDateTime createdAt) {
        this.createdAt = createdAt;
    }

    public LocalDateTime getUpdatedAt() {
        return updatedAt;
    }

    public void setUpdatedAt(LocalDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
}
