package com.sagopalgo.api.dashboard.dto;

/**
 * 대시보드 스냅샷에 포함되는 앱 알림 요약 DTO입니다.
 */
public record DashboardAlertResponse(
    Long alertId,
    String title,
    String body,
    String timeLabel,
    String type,
    boolean read
) {
}
