package com.sagopalgo.api.oauth;

/**
 * 사고팔고에서 허용하는 소셜 로그인 제공자입니다.
 *
 * <p>기획 변경에 따라 이메일/비밀번호 로그인은 제거하고, 현재는 Google과 Naver만 인증 제공자로
 * 인정합니다.</p>
 */
public enum OAuthProvider {
    GOOGLE,
    NAVER
}
