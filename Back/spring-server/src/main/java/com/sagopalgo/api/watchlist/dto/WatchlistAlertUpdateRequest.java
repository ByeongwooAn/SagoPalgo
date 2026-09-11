package com.sagopalgo.api.watchlist.dto;

import jakarta.validation.constraints.NotNull;

/**
 * 관심 종목 알림 설정 변경 요청 DTO입니다.
 */
public record WatchlistAlertUpdateRequest(
    @NotNull(message = "알림 설정 여부는 필수입니다.")
    Boolean alertEnabled
) {
}
