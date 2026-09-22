package com.sagopalgo.api.config;

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
}
