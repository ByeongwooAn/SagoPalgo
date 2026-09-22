package com.sagopalgo.api.order.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 증권사 주문을 호출하지 않고 저장하는 주문 사전검증 감사 로그입니다.
 */
public class OrderPrecheckRecord {

    private Long orderPrecheckId;
    private Long userId;
    private String stockCode;
    private String stockName;
    private String market;
    private String orderSide;
    private String orderType;
    private BigDecimal requestedPrice;
    private BigDecimal quantity;
    private BigDecimal estimatedAmount;
    private String quoteProvider;
    private BigDecimal currentPrice;
    private BigDecimal orderAvailableCash;
    private BigDecimal orderableQuantity;
    private boolean orderEnabled;
    private boolean eligible;
    private String blockerSummary;
    private LocalDateTime createdAt;

    public Long getOrderPrecheckId() { return orderPrecheckId; }
    public void setOrderPrecheckId(Long orderPrecheckId) { this.orderPrecheckId = orderPrecheckId; }
    public Long getUserId() { return userId; }
    public void setUserId(Long userId) { this.userId = userId; }
    public String getStockCode() { return stockCode; }
    public void setStockCode(String stockCode) { this.stockCode = stockCode; }
    public String getStockName() { return stockName; }
    public void setStockName(String stockName) { this.stockName = stockName; }
    public String getMarket() { return market; }
    public void setMarket(String market) { this.market = market; }
    public String getOrderSide() { return orderSide; }
    public void setOrderSide(String orderSide) { this.orderSide = orderSide; }
    public String getOrderType() { return orderType; }
    public void setOrderType(String orderType) { this.orderType = orderType; }
    public BigDecimal getRequestedPrice() { return requestedPrice; }
    public void setRequestedPrice(BigDecimal requestedPrice) { this.requestedPrice = requestedPrice; }
    public BigDecimal getQuantity() { return quantity; }
    public void setQuantity(BigDecimal quantity) { this.quantity = quantity; }
    public BigDecimal getEstimatedAmount() { return estimatedAmount; }
    public void setEstimatedAmount(BigDecimal estimatedAmount) { this.estimatedAmount = estimatedAmount; }
    public String getQuoteProvider() { return quoteProvider; }
    public void setQuoteProvider(String quoteProvider) { this.quoteProvider = quoteProvider; }
    public BigDecimal getCurrentPrice() { return currentPrice; }
    public void setCurrentPrice(BigDecimal currentPrice) { this.currentPrice = currentPrice; }
    public BigDecimal getOrderAvailableCash() { return orderAvailableCash; }
    public void setOrderAvailableCash(BigDecimal orderAvailableCash) { this.orderAvailableCash = orderAvailableCash; }
    public BigDecimal getOrderableQuantity() { return orderableQuantity; }
    public void setOrderableQuantity(BigDecimal orderableQuantity) { this.orderableQuantity = orderableQuantity; }
    public boolean isOrderEnabled() { return orderEnabled; }
    public void setOrderEnabled(boolean orderEnabled) { this.orderEnabled = orderEnabled; }
    public boolean isEligible() { return eligible; }
    public void setEligible(boolean eligible) { this.eligible = eligible; }
    public String getBlockerSummary() { return blockerSummary; }
    public void setBlockerSummary(String blockerSummary) { this.blockerSummary = blockerSummary; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public void setCreatedAt(LocalDateTime createdAt) { this.createdAt = createdAt; }
}
