package com.sagopalgo.api.oauth.client;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.OAuthProperties;
import com.sagopalgo.api.oauth.OAuthProvider;
import com.sagopalgo.api.oauth.dto.OAuthUserProfile;
import io.jsonwebtoken.Claims;
import io.jsonwebtoken.JwsHeader;
import io.jsonwebtoken.JwtException;
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SigningKeyResolverAdapter;
import java.math.BigInteger;
import java.security.Key;
import java.security.KeyFactory;
import java.security.NoSuchAlgorithmException;
import java.security.PublicKey;
import java.security.spec.InvalidKeySpecException;
import java.security.spec.RSAPublicKeySpec;
import java.time.Instant;
import java.util.Base64;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * Google 공식 OpenID Connect 방식으로 ID token을 검증하는 클라이언트입니다.
 *
 * <p>Google 문서 기준에 맞춰 ID token 서명은 JWKS 공개키로 검증하고, aud/iss/exp 클레임을 확인한 뒤
 * 절대 변하지 않는 sub 값을 사고팔고의 provider_user_id로 사용합니다.</p>
 */
@Component
public class GoogleOAuthClient implements SocialOAuthClient {

    private static final List<String> ALLOWED_ISSUERS = List.of("https://accounts.google.com", "accounts.google.com");
    private static final long JWKS_CACHE_SECONDS = 21_600L;

    private final OAuthProperties oauthProperties;
    private final RestClient restClient;
    private final Map<String, PublicKey> cachedKeys = new ConcurrentHashMap<>();
    private Instant cachedUntil = Instant.EPOCH;

    /**
     * Google OAuth 설정과 외부 API 호출 클라이언트를 주입받습니다.
     *
     * @param oauthProperties Google client id와 JWKS URI 설정입니다.
     * @param restClient Google JWKS 호출에 사용할 HTTP 클라이언트입니다.
     */
    public GoogleOAuthClient(OAuthProperties oauthProperties, RestClient restClient) {
        this.oauthProperties = oauthProperties;
        this.restClient = restClient;
    }

    /**
     * Google ID token을 검증하고 내부 사용자 프로필로 변환합니다.
     *
     * @param providerToken Flutter 앱이 Google 로그인 SDK에서 받은 ID token입니다.
     * @return 검증된 Google 사용자 프로필입니다.
     */
    @Override
    public OAuthUserProfile fetchProfile(String providerToken) {
        ensureGoogleClientIdConfigured();

        try {
            Claims claims = Jwts.parserBuilder()
                .setSigningKeyResolver(new GoogleSigningKeyResolver())
                .requireAudience(oauthProperties.google().clientId())
                .build()
                .parseClaimsJws(providerToken)
                .getBody();

            validateIssuer(claims);
            validateEmailVerified(claims);

            return new OAuthUserProfile(
                OAuthProvider.GOOGLE,
                claims.getSubject(),
                claims.get("email", String.class),
                claims.get("name", String.class),
                claims.get("picture", String.class)
            );
        } catch (JwtException | IllegalArgumentException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google ID token이 유효하지 않습니다.");
        }
    }

    /**
     * Google OAuth Client ID가 비어 있으면 토큰의 aud 검증을 할 수 없으므로 요청을 거부합니다.
     */
    private void ensureGoogleClientIdConfigured() {
        if (!StringUtils.hasText(oauthProperties.google().clientId())) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "Google OAuth Client ID가 설정되어 있지 않습니다.");
        }
    }

    /**
     * Google ID token의 발급자가 공식 발급자인지 확인합니다.
     *
     * @param claims 검증된 JWT Claims입니다.
     */
    private void validateIssuer(Claims claims) {
        if (!ALLOWED_ISSUERS.contains(claims.getIssuer())) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google ID token 발급자가 올바르지 않습니다.");
        }
    }

    /**
     * Google 계정 이메일이 검증된 이메일인지 확인합니다.
     *
     * @param claims 검증된 JWT Claims입니다.
     */
    private void validateEmailVerified(Claims claims) {
        Object emailVerified = claims.get("email_verified");
        if (emailVerified instanceof Boolean verified && verified) {
            return;
        }
        if (emailVerified instanceof String verified && Boolean.parseBoolean(verified)) {
            return;
        }

        throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "검증되지 않은 Google 이메일입니다.");
    }

    /**
     * Google JWKS를 가져와 kid별 RSA 공개키 캐시를 갱신합니다.
     */
    private synchronized void refreshGooglePublicKeys() {
        if (Instant.now().isBefore(cachedUntil) && !cachedKeys.isEmpty()) {
            return;
        }

        GoogleJwksResponse response;
        try {
            response = restClient.get()
                .uri(oauthProperties.google().jwksUri())
                .retrieve()
                .body(GoogleJwksResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google 공개키를 조회하지 못했습니다.");
        }

        if (response == null || response.keys() == null || response.keys().isEmpty()) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google 공개키를 조회하지 못했습니다.");
        }

        cachedKeys.clear();
        for (GoogleJwk jwk : response.keys()) {
            cachedKeys.put(jwk.kid(), toPublicKey(jwk));
        }
        cachedUntil = Instant.now().plusSeconds(JWKS_CACHE_SECONDS);
    }

    /**
     * Google JWK의 n/e 값을 Java RSA PublicKey로 변환합니다.
     *
     * @param jwk Google JWKS 응답에 포함된 RSA 공개키 정보입니다.
     * @return JWT 서명 검증에 사용할 RSA 공개키입니다.
     */
    private PublicKey toPublicKey(GoogleJwk jwk) {
        try {
            BigInteger modulus = new BigInteger(1, Base64.getUrlDecoder().decode(jwk.n()));
            BigInteger exponent = new BigInteger(1, Base64.getUrlDecoder().decode(jwk.e()));
            return KeyFactory.getInstance("RSA").generatePublic(new RSAPublicKeySpec(modulus, exponent));
        } catch (NoSuchAlgorithmException | InvalidKeySpecException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google 공개키를 처리하지 못했습니다.");
        }
    }

    /**
     * JWT header의 kid 값에 맞는 Google 공개키를 찾아 JJWT 파서에 넘겨주는 resolver입니다.
     */
    private class GoogleSigningKeyResolver extends SigningKeyResolverAdapter {

        /**
         * Google ID token header의 kid로 공개키를 찾습니다.
         *
         * @param header JWT header입니다.
         * @param claims JWT claims입니다.
         * @return kid에 해당하는 Google RSA 공개키입니다.
         */
        @Override
        public Key resolveSigningKey(JwsHeader header, Claims claims) {
            String keyId = header.getKeyId();
            refreshGooglePublicKeys();

            PublicKey publicKey = cachedKeys.get(keyId);
            if (publicKey == null) {
                cachedUntil = Instant.EPOCH;
                refreshGooglePublicKeys();
                publicKey = cachedKeys.get(keyId);
            }

            if (publicKey == null) {
                throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Google ID token 공개키를 찾을 수 없습니다.");
            }

            return publicKey;
        }
    }

    /**
     * Google JWKS 응답의 최상위 JSON 구조입니다.
     *
     * @param keys Google 공개키 목록입니다.
     */
    private record GoogleJwksResponse(List<GoogleJwk> keys) {
    }

    /**
     * Google JWKS의 개별 RSA 공개키입니다.
     *
     * @param kid JWT header의 kid와 매칭되는 키 ID입니다.
     * @param kty 키 타입입니다.
     * @param alg 서명 알고리즘입니다.
     * @param use 키 용도입니다.
     * @param n RSA modulus입니다.
     * @param e RSA public exponent입니다.
     */
    private record GoogleJwk(
        String kid,
        String kty,
        String alg,
        String use,
        String n,
        String e
    ) {
    }
}
