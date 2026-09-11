package com.sagopalgo.api.oauth.client;

import com.sagopalgo.api.oauth.dto.OAuthUserProfile;

/**
 * 소셜 로그인 제공자별 토큰 검증 클라이언트가 따라야 하는 공통 인터페이스입니다.
 *
 * <p>Google은 ID token을 검증하고, Naver는 서버에서 확보한 access token으로 프로필 API를 호출하지만,
 * 인증 서비스는 둘 다 OAuthUserProfile만 받도록 추상화합니다.</p>
 */
public interface SocialOAuthClient {

    /**
     * 외부 제공자 토큰을 검증한 뒤 사고팔고 내부 사용자 프로필로 변환합니다.
     *
     * @param providerToken Google ID token 또는 서버에서 확보한 Naver access token입니다.
     * @return 검증된 외부 사용자 프로필입니다.
     */
    OAuthUserProfile fetchProfile(String providerToken);
}
