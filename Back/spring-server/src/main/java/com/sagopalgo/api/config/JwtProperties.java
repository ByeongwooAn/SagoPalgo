package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * application.yml의 sagopalgo.jwt 설정을 Java 객체로 바인딩하는 설정 클래스입니다.
 *
 * <p>토큰 만료 시간과 서명 키를 코드에 직접 박아두지 않고 설정으로 분리하면,
 * 로컬/테스트/운영 환경마다 안전하게 다른 값을 사용할 수 있습니다.</p>
 *
 * @param secret JWT HMAC 서명에 사용할 비밀 키입니다.
 * @param accessTokenExpirationMinutes access token 만료 시간입니다.
 * @param refreshTokenExpirationDays refresh token 만료 일수입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.jwt")
public record JwtProperties(
    String secret,
    long accessTokenExpirationMinutes,
    long refreshTokenExpirationDays
) {
}
