package com.sagopalgo.api.watchlist.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

/**
 * 관심 종목 추가 요청 DTO입니다.
 */
public record WatchlistCreateRequest(
    @NotBlank(message = "종목 코드는 필수입니다.")
    String stockCode,

    @NotBlank(message = "종목명은 필수입니다.")
    String stockName,

    @NotBlank(message = "시장은 필수입니다.")
    String market,

    @NotNull(message = "알림 설정 여부는 필수입니다.")
    Boolean alertEnabled
) {
}
