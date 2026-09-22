package com.sagopalgo.api.alert.dto;

import java.util.List;

/**
 * 페이지 정보와 알림 목록을 함께 반환합니다.
 */
public record AlertListResponse(
    List<AlertResponse> items,
    int page,
    int size,
    long total
) {
}
