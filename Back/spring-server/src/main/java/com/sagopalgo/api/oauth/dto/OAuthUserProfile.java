package com.sagopalgo.api.oauth.dto;

import com.sagopalgo.api.oauth.OAuthProvider;

/**
 * 외부 소셜 로그인 제공자에서 검증된 사용자 정보를 내부 인증 서비스가 쓰기 쉬운 형태로 정규화한 DTO입니다.
 *
 * @param provider 로그인 제공자입니다.
 * @param providerUserId 제공자 내부에서 보장하는 사용자 고유 ID입니다.
 * @param email 사용자가 동의한 경우 내려오는 이메일입니다.
 * @param nickname 앱에 표시할 이름입니다.
 * @param profileImageUrl 제공자가 내려준 프로필 이미지 URL입니다.
 */
public record OAuthUserProfile(
    OAuthProvider provider,
    String providerUserId,
    String email,
    String nickname,
    String profileImageUrl
) {
}
