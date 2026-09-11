package com.sagopalgo.api.auth.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * Naver authorization code 로그인 요청입니다.
 *
 * <p>모바일 앱은 Client Secret을 들고 있지 않고, Naver callback으로 받은 code/state/redirectUri만
 * 백엔드에 전달합니다. 백엔드는 서버 환경 변수의 Client Secret으로 access token을 교환합니다.</p>
 *
 * @param authorizationCode Naver callback query의 code 값입니다.
 * @param state Naver authorization 요청과 callback을 매칭하는 CSRF 방지 값입니다.
 */
public record NaverLoginRequest(
    @NotBlank(message = "Naver authorization code는 필수입니다.")
    String authorizationCode,

    @NotBlank(message = "Naver state는 필수입니다.")
    String state
) {
}
