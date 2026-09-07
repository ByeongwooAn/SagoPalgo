package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Google/Naver 소셜 로그인 검증에 필요한 설정값을 바인딩하는 클래스입니다.
 *
 * <p>클라이언트 ID, Secret, 공식 API 엔드포인트는 환경마다 달라질 수 있으므로 코드에 직접 쓰지 않고
 * application.yml과 환경 변수에서 주입받습니다.</p>
 *
 * @param google Google 로그인 검증 설정입니다.
 * @param naver Naver 로그인 검증 설정입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.oauth")
public record OAuthProperties(
    Google google,
    Naver naver
) {

    /**
     * Google ID token 검증에 필요한 설정입니다.
     *
     * @param clientId Google Cloud Console에서 발급받은 Android/Web OAuth Client ID입니다.
     * @param jwksUri Google OpenID Connect 공개키 JWKS 엔드포인트입니다.
     */
    public record Google(
        String clientId,
        String jwksUri
    ) {
    }

    /**
     * Naver 프로필 API 호출에 필요한 설정입니다.
     *
     * @param clientId Naver Developers에서 발급받은 Client ID입니다.
     * @param clientSecret Naver Developers에서 발급받은 Client Secret입니다.
     * @param profileUri Naver 회원 프로필 조회 API 엔드포인트입니다.
     */
    public record Naver(
        String clientId,
        String clientSecret,
        String profileUri
    ) {
    }
}
