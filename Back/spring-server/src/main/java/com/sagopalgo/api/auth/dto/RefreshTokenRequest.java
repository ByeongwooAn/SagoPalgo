package com.sagopalgo.api.auth.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * access token 재발급 API가 클라이언트에서 받는 요청 DTO입니다.
 *
 * @param refreshToken 로그인 또는 이전 재발급 때 받은 refresh token 원문입니다.
 */
public record RefreshTokenRequest(
    @NotBlank(message = "refresh token은 필수입니다.")
    String refreshToken
) {
}
