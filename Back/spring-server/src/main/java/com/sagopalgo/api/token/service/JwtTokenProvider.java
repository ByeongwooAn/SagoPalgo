package com.sagopalgo.api.token.service;

import com.sagopalgo.api.config.JwtProperties;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import com.sagopalgo.api.user.model.User;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;
import io.jsonwebtoken.security.Keys;
import java.nio.charset.StandardCharsets;
import java.security.Key;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.Map;
import org.springframework.stereotype.Component;

/**
 * JWT access token과 refresh token을 생성하는 컴포넌트입니다.
 *
 * <p>이 클래스는 토큰 생성뿐 아니라 요청 헤더로 들어온 토큰을 검증하고, Spring Security에서
 * 사용할 사용자 인증 객체로 변환하는 책임까지 가집니다.</p>
 */
@Component
public class JwtTokenProvider {

    private final JwtProperties jwtProperties;

    /**
     * application.yml에서 바인딩된 JWT 설정을 주입받습니다.
     *
     * @param jwtProperties JWT 서명 키와 만료 시간 설정입니다.
     */
    public JwtTokenProvider(JwtProperties jwtProperties) {
        this.jwtProperties = jwtProperties;
    }

    /**
     * 앱이 API 호출 시 Authorization 헤더에 넣을 access token을 생성합니다.
     *
     * @param user 토큰의 주체가 되는 로그인 사용자입니다.
     * @return 서명된 JWT access token 문자열입니다.
     */
    public String createAccessToken(User user) {
        Instant now = Instant.now();
        Instant expiresAt = now.plus(jwtProperties.accessTokenExpirationMinutes(), ChronoUnit.MINUTES);

        Map<String, Object> claims = new java.util.HashMap<>();
        putIfNotNull(claims, "email", user.getEmail());
        putIfNotNull(claims, "nickname", user.getNickname());
        putIfNotNull(claims, "role", user.getRole());

        return Jwts.builder()
            .setSubject(String.valueOf(user.getUserId()))
            .addClaims(claims)
            .setIssuedAt(Date.from(now))
            .setExpiration(Date.from(expiresAt))
            .signWith(signingKey(), SignatureAlgorithm.HS256)
            .compact();
    }

    /**
     * access token을 검증하고 인증된 사용자 정보를 추출합니다.
     *
     * <p>refresh token은 type 클레임이 "refresh"로 들어가므로 access token 자리에서 사용되면
     * 거부합니다. 이렇게 해야 refresh token이 API 호출 인증 수단으로 오용되지 않습니다.</p>
     *
     * @param token Authorization 헤더에서 꺼낸 Bearer 토큰입니다.
     * @return Spring Security 인증 principal로 사용할 사용자 정보입니다.
     */
    public JwtAuthenticatedUser parseAccessToken(String token) {
        Claims claims = parseClaims(token);
        if ("refresh".equals(claims.get("type", String.class))) {
            throw new JwtException("refresh token은 access token으로 사용할 수 없습니다.");
        }

        return new JwtAuthenticatedUser(
            Long.valueOf(claims.getSubject()),
            claims.get("email", String.class),
            claims.get("nickname", String.class),
            claims.get("role", String.class)
        );
    }

    /**
     * refresh token을 검증하고 토큰 주체인 사용자 ID를 추출합니다.
     *
     * @param refreshToken access token 재발급 요청에 담긴 refresh token입니다.
     * @return refresh token의 subject에 저장된 사용자 ID입니다.
     */
    public Long parseRefreshTokenSubject(String refreshToken) {
        Claims claims = parseClaims(refreshToken);
        if (!"refresh".equals(claims.get("type", String.class))) {
            throw new JwtException("refresh token 형식이 아닙니다.");
        }

        return Long.valueOf(claims.getSubject());
    }

    /**
     * access token 재발급에 사용할 refresh token을 생성합니다.
     *
     * @param user 토큰의 주체가 되는 로그인 사용자입니다.
     * @return 서명된 JWT refresh token 문자열입니다.
     */
    public String createRefreshToken(User user) {
        Instant now = Instant.now();
        Instant expiresAt = now.plus(jwtProperties.refreshTokenExpirationDays(), ChronoUnit.DAYS);

        return Jwts.builder()
            .setSubject(String.valueOf(user.getUserId()))
            .claim("type", "refresh")
            .setIssuedAt(Date.from(now))
            .setExpiration(Date.from(expiresAt))
            .signWith(signingKey(), SignatureAlgorithm.HS256)
            .compact();
    }

    /**
     * API 응답에 expiresIn 초 단위 값을 내려주기 위해 access token 만료 시간을 계산합니다.
     *
     * @return access token 유효 시간(초)입니다.
     */
    public long accessTokenExpiresInSeconds() {
        return jwtProperties.accessTokenExpirationMinutes() * 60;
    }

    /**
     * refresh token DB 저장 시 사용할 만료 시각을 계산합니다.
     *
     * @return 현재 시각 기준 refresh token 만료 시각입니다.
     */
    public Instant refreshTokenExpiresAt() {
        return Instant.now().plus(jwtProperties.refreshTokenExpirationDays(), ChronoUnit.DAYS);
    }

    /**
     * 문자열 secret을 HMAC-SHA 서명 키로 변환합니다.
     *
     * @return JWT 서명에 사용할 Key 객체입니다.
     */
    private Key signingKey() {
        return Keys.hmacShaKeyFor(jwtProperties.secret().getBytes(StandardCharsets.UTF_8));
    }

    /**
     * JWT 서명과 만료 시간을 검증한 뒤 Claims를 반환합니다.
     *
     * @param token 검증할 JWT 문자열입니다.
     * @return 검증이 끝난 JWT Claims입니다.
     */
    private Claims parseClaims(String token) {
        return Jwts.parserBuilder()
            .setSigningKey(signingKey())
            .build()
            .parseClaimsJws(token)
            .getBody();
    }

    /**
     * null이 아닌 값만 JWT 클레임에 추가합니다.
     *
     * <p>Naver 이메일처럼 사용자 동의 범위에 따라 내려오지 않을 수 있는 값이 있으므로,
     * null 값을 그대로 넣지 않고 생략해 토큰 생성 오류를 방지합니다.</p>
     *
     * @param claims JWT에 넣을 클레임 Map입니다.
     * @param key 클레임 이름입니다.
     * @param value 클레임 값입니다.
     */
    private void putIfNotNull(Map<String, Object> claims, String key, Object value) {
        if (value != null) {
            claims.put(key, value);
        }
    }
}
