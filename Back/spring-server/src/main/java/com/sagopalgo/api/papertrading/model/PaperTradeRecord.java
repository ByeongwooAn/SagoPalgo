package com.sagopalgo.api.papertrading.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 실제 주문과 분리해 저장하는 모의매매 원장의 한 행입니다.
 */
public class PaperTradeRecord {

    private Long tradeRecordId;
    private Long userId;
    private Long recommendationId;
    private String requestId;
    private String stockCode;
    private String stockName;
    private String market;
    private String tradeType;
    private String executionMode;
    private BigDecimal tradePrice;
    private BigDecimal quantity;
    private BigDecimal realizedProfit;
    private LocalDateTime tradeDate;
    private String memo;
    private LocalDateTime createdAt;

    public Long getTradeRecordId() { return tradeRecordId; }
    public void setTradeRecordId(Long tradeRecordId) { this.tradeRecordId = tradeRecordId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public Long getRecommendationId() { return recommendationId; }
    public void setRecommendationId(Long recommendationId) { this.recommendationId = recommendationId; }
    public String getRequestId() { return requestId; }
    public void setRequestId(String requestId) { this.requestId = requestId; }
    public String getStockCode() { return stockCode; }
    public void setStockCode(String stockCode) { this.stockCode = stockCode; }
    public String getStockName() { return stockName; }
    public void setStockName(String stockName) { this.stockName = stockName; }
    public String getMarket() { return market; }
    public void setMarket(String market) { this.market = market; }
    public String getTradeType() { return tradeType; }
    public void setTradeType(String tradeType) { this.tradeType = tradeType; }
    public String getExecutionMode() { return executionMode; }
    public void setExecutionMode(String executionMode) { this.executionMode = executionMode; }
    public BigDecimal getTradePrice() { return tradePrice; }
    public void setTradePrice(BigDecimal tradePrice) { this.tradePrice = tradePrice; }
    public BigDecimal getQuantity() { return quantity; }
    public void setQuantity(BigDecimal quantity) { this.quantity = quantity; }
    public BigDecimal getRealizedProfit() { return realizedProfit; }
    public void setRealizedProfit(BigDecimal realizedProfit) { this.realizedProfit = realizedProfit; }
    public LocalDateTime getTradeDate() { return tradeDate; }
    public void setTradeDate(LocalDateTime tradeDate) { this.tradeDate = tradeDate; }
    public String getMemo() { return memo; }
    public void setMemo(String memo) { this.memo = memo; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
