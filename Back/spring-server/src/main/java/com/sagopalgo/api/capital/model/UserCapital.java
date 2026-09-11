package com.sagopalgo.api.capital.model;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * user_capital 테이블의 한 행을 표현하는 모델입니다.
 */
public class UserCapital {

    private Long capitalId;
    private Long userId;
    private BigDecimal availableCapital;
    private BigDecimal riskPerTradeRate;
    private BigDecimal recommendedMinPosition;
    private BigDecimal recommendedMaxPosition;
    private LocalDateTime createdAt;
    private LocalDateTime updatedAt;

    public Long getCapitalId() {
        return capitalId;
    }

    public void setCapitalId(Long capitalId) {
        this.capitalId = capitalId;
    }

    public Long getUserId() {
        return userId;
    }

    public void setUserId(Long userId) {
        this.userId = userId;
    }

    public BigDecimal getAvailableCapital() {
        return availableCapital;
    }

    public void setAvailableCapital(BigDecimal availableCapital) {
        this.availableCapital = availableCapital;
    }

    public BigDecimal getRiskPerTradeRate() {
        return riskPerTradeRate;
    }

    public void setRiskPerTradeRate(BigDecimal riskPerTradeRate) {
        this.riskPerTradeRate = riskPerTradeRate;
    }

    public BigDecimal getRecommendedMinPosition() {
        return recommendedMinPosition;
    }

    public void setRecommendedMinPosition(BigDecimal recommendedMinPosition) {
        this.recommendedMinPosition = recommendedMinPosition;
    }

    public BigDecimal getRecommendedMaxPosition() {
        return recommendedMaxPosition;
    }

    public void setRecommendedMaxPosition(BigDecimal recommendedMaxPosition) {
        this.recommendedMaxPosition = recommendedMaxPosition;
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
