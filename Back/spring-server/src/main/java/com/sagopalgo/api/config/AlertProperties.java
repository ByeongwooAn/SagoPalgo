package com.sagopalgo.api.config;

import java.math.BigDecimal;
import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 추천 신호 알림 생성 주기와 중복 방지 기준입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.alerts")
public class AlertProperties {

    private boolean analysisEnabled = false;
    private String cron = "0 0/15 * * * *";
    private String zone = "Asia/Seoul";
    private int cooldownMinutes = 60;
    private boolean priceEventsEnabled = true;
    private BigDecimal volatilityThresholdRate = new BigDecimal("5.0");
    private boolean researchEventsEnabled = true;
    private int newsMaxAgeHours = 24;
    private int disclosureMaxAgeDays = 1;

    public boolean isAnalysisEnabled() {
        return analysisEnabled;
    }

    public void setAnalysisEnabled(boolean analysisEnabled) {
        this.analysisEnabled = analysisEnabled;
    }

    public String getCron() {
        return cron;
    }

    public void setCron(String cron) {
        this.cron = cron;
    }

    public String getZone() {
        return zone;
    }

    public void setZone(String zone) {
        this.zone = zone;
    }

    public int getCooldownMinutes() {
        return cooldownMinutes;
    }

    public void setCooldownMinutes(int cooldownMinutes) {
        this.cooldownMinutes = cooldownMinutes;
    }

    public boolean isPriceEventsEnabled() {
        return priceEventsEnabled;
    }

    public void setPriceEventsEnabled(boolean priceEventsEnabled) {
        this.priceEventsEnabled = priceEventsEnabled;
    }

    public BigDecimal getVolatilityThresholdRate() {
        return volatilityThresholdRate;
    }

    public void setVolatilityThresholdRate(BigDecimal volatilityThresholdRate) {
        this.volatilityThresholdRate = volatilityThresholdRate;
    }

    public boolean isResearchEventsEnabled() {
        return researchEventsEnabled;
    }

    public void setResearchEventsEnabled(boolean researchEventsEnabled) {
        this.researchEventsEnabled = researchEventsEnabled;
    }

    public int getNewsMaxAgeHours() {
        return newsMaxAgeHours;
    }

    public void setNewsMaxAgeHours(int newsMaxAgeHours) {
        this.newsMaxAgeHours = newsMaxAgeHours;
    }

    public int getDisclosureMaxAgeDays() {
        return disclosureMaxAgeDays;
    }

    public void setDisclosureMaxAgeDays(int disclosureMaxAgeDays) {
        this.disclosureMaxAgeDays = disclosureMaxAgeDays;
    }
}
