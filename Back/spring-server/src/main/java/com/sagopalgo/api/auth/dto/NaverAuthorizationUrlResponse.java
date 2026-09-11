package com.sagopalgo.api.auth.dto;

/**
 * Naver 로그인 인증 화면으로 이동할 URL 응답입니다.
 *
 * @param authorizationUrl Naver OAuth authorization endpoint와 필수 query parameter를 조합한 URL입니다.
 * @param redirectUri 앱이 callback을 기다릴 Naver redirect URI입니다.
 */
public record NaverAuthorizationUrlResponse(
    String authorizationUrl,
    String redirectUri
) {
}
