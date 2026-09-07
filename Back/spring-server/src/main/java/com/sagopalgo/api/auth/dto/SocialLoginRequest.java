package com.sagopalgo.api.auth.dto;

import jakarta.validation.constraints.NotBlank;

/**
 * Google/Naver 소셜 로그인 API가 클라이언트에서 받는 요청 DTO입니다.
 *
 * <p>Google 로그인에서는 Google SDK가 내려준 ID token을, Naver 로그인에서는 Naver SDK가 내려준
 * access token을 providerToken에 담아 서버로 전달합니다.</p>
 *
 * @param providerToken 소셜 제공자에서 발급받은 인증 토큰입니다.
 */
public record SocialLoginRequest(
    @NotBlank(message = "소셜 로그인 토큰은 필수입니다.")
    String providerToken
) {
}
