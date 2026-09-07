package com.sagopalgo.api.auth.dto;

/**
 * 로그인 성공 시 토큰과 사용자 정보를 함께 내려주는 응답 DTO입니다.
 *
 * @param accessToken API 인증 헤더에 사용할 JWT access token입니다.
 * @param refreshToken access token 재발급에 사용할 JWT refresh token입니다.
 * @param expiresIn access token 만료까지 남은 초 단위 시간입니다.
 * @param user 로그인한 사용자 기본 정보입니다.
 */
public record AuthTokenResponse(
    String accessToken,
    String refreshToken,
    long expiresIn,
    UserResponse user
) {
}
