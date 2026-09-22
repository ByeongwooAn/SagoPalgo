package com.sagopalgo.api.alert.dto;

import com.sagopalgo.api.alert.model.AlertRecord;
import java.time.Duration;
import java.time.LocalDateTime;

/**
 * Flutter 알림 목록과 Windows 토스트 전달에 사용하는 응답입니다.
 */
public record AlertResponse(
    Long alertId,
    Long recommendationId,
    String type,
    String title,
    String body,
    boolean read,
    LocalDateTime sentAt,
    LocalDateTime createdAt,
    String timeLabel
) {

    public static AlertResponse from(AlertRecord record) {
        return new AlertResponse(
            record.getAlertId(),
            record.getRecommendationId(),
            record.getAlertType(),
            record.getTitle(),
            record.getBody(),
            record.isRead(),
            record.getSentAt(),
            record.getCreatedAt(),
            timeLabel(record.getCreatedAt())
        );
    }

    private static String timeLabel(LocalDateTime createdAt) {
        if (createdAt == null) {
            return "방금 전";
        }
        long minutes = Math.max(0, Duration.between(createdAt, LocalDateTime.now()).toMinutes());
        if (minutes < 1) {
            return "방금 전";
        }
        if (minutes < 60) {
            return minutes + "분 전";
        }
        long hours = minutes / 60;
        if (hours < 24) {
            return hours + "시간 전";
        }
        return (hours / 24) + "일 전";
    }
}
