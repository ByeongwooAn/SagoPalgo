package com.sagopalgo.api.oauth.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.OAuthProperties;
import com.sagopalgo.api.oauth.OAuthProvider;
import com.sagopalgo.api.oauth.dto.OAuthUserProfile;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Naver authorization code를 access token으로 교환하고 공식 프로필 API를 호출하는 클라이언트입니다.
 *
 * <p>모바일 앱에는 Client Secret을 넣지 않고, 서버가 code/token 교환과 프로필 조회를 담당합니다.
 * 프로필 응답의 response.id 값을 사고팔고의 provider_user_id로 사용합니다.</p>
 */
@Component
public class NaverOAuthClient implements SocialOAuthClient {

    private final OAuthProperties oauthProperties;
    private final RestClient restClient;

    /**
     * Naver OAuth 설정과 외부 API 호출 클라이언트를 주입받습니다.
     *
     * @param oauthProperties Naver Client ID/Secret과 프로필 API URI 설정입니다.
     * @param restClient Naver 프로필 API 호출에 사용할 HTTP 클라이언트입니다.
     */
    public NaverOAuthClient(OAuthProperties oauthProperties, RestClient restClient) {
        this.oauthProperties = oauthProperties;
        this.restClient = restClient;
    }

    /**
     * 이미 서버에서 확보한 Naver access token으로 프로필을 조회합니다.
     *
     * @param providerToken Naver access token입니다.
     * @return 검증된 Naver 사용자 프로필입니다.
     */
    @Override
    public OAuthUserProfile fetchProfile(String providerToken) {
        ensureNaverClientConfigured();
        ensureText(providerToken, "Naver access token은 필수입니다.");
        return fetchProfileByAccessToken(providerToken);
    }

    /**
     * Naver 로그인 인증 화면 URL을 생성합니다.
     *
     * @param state CSRF 방지를 위해 앱이 생성한 상태값입니다.
     * @return Naver authorization endpoint URL입니다.
     */
    public String authorizationUrl(String state) {
        ensureNaverClientConfigured();
        ensureText(state, "Naver state는 필수입니다.");
        ensureText(redirectUri(), "Naver redirect URI는 필수입니다.");

        return UriComponentsBuilder
            .fromUriString(oauthProperties.naver().authorizeUri())
            .queryParam("response_type", "code")
            .queryParam("client_id", oauthProperties.naver().clientId())
            .queryParam("redirect_uri", redirectUri())
            .queryParam("state", state)
            .build()
            .encode()
            .toUriString();
    }

    /**
     * 서버 환경에 설정된 Naver callback URL입니다.
     *
     * @return Naver Developers에 등록한 redirect URI입니다.
     */
    public String redirectUri() {
        return oauthProperties.naver().redirectUri();
    }

    /**
     * Naver authorization code를 access token으로 교환한 뒤 프로필 API를 호출합니다.
     *
     * @param authorizationCode Naver callback으로 받은 authorization code입니다.
     * @param state authorization URL 생성 때 사용한 CSRF 방지 상태값입니다.
     * @return 검증된 Naver 사용자 프로필입니다.
     */
    public OAuthUserProfile fetchProfile(String authorizationCode, String state) {
        ensureNaverClientConfigured();
        ensureText(authorizationCode, "Naver authorization code는 필수입니다.");
        ensureText(state, "Naver state는 필수입니다.");

        String accessToken = exchangeAuthorizationCode(authorizationCode, state);
        return fetchProfileByAccessToken(accessToken);
    }

    /**
     * Naver access token으로 프로필 API를 호출하고 내부 사용자 프로필로 변환합니다.
     *
     * @param accessToken Naver token API에서 받은 access token입니다.
     * @return 검증된 Naver 사용자 프로필입니다.
     */
    private OAuthUserProfile fetchProfileByAccessToken(String accessToken) {
        NaverProfileResponse profileResponse;
        try {
            profileResponse = restClient.get()
                .uri(oauthProperties.naver().profileUri())
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken)
                .header("X-Naver-Client-Id", oauthProperties.naver().clientId())
                .header("X-Naver-Client-Secret", oauthProperties.naver().clientSecret())
                .retrieve()
                .body(NaverProfileResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Naver access token이 유효하지 않습니다.");
        }

        if (profileResponse == null || !"00".equals(profileResponse.resultcode()) || profileResponse.response() == null) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Naver access token이 유효하지 않습니다.");
        }

        Map<String, Object> response = profileResponse.response();
        String providerUserId = asString(response.get("id"));
        if (!StringUtils.hasText(providerUserId)) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Naver 프로필 ID를 확인하지 못했습니다.");
        }

        return new OAuthUserProfile(
            OAuthProvider.NAVER,
            providerUserId,
            asString(response.get("email")),
            asString(response.getOrDefault("nickname", response.get("name"))),
            asString(response.get("profile_image"))
        );
    }

    /**
     * Naver token API로 authorization code를 access token으로 교환합니다.
     *
     * @param authorizationCode Naver callback으로 받은 authorization code입니다.
     * @param state authorization URL 생성 때 사용한 CSRF 방지 상태값입니다.
     * @return Naver access token입니다.
     */
    private String exchangeAuthorizationCode(String authorizationCode, String state) {
        NaverTokenResponse tokenResponse;
        try {
            tokenResponse = restClient.get()
                .uri(UriComponentsBuilder
                    .fromUriString(oauthProperties.naver().tokenUri())
                    .queryParam("grant_type", "authorization_code")
                    .queryParam("client_id", oauthProperties.naver().clientId())
                    .queryParam("client_secret", oauthProperties.naver().clientSecret())
                    .queryParam("code", authorizationCode)
                    .queryParam("state", state)
                    .build()
                    .encode()
                    .toUri()
                )
                .retrieve()
                .body(NaverTokenResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Naver authorization code가 유효하지 않습니다.");
        }

        if (tokenResponse == null || !StringUtils.hasText(tokenResponse.accessToken())) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "Naver access token을 발급받지 못했습니다.");
        }

        return tokenResponse.accessToken();
    }

    /**
     * Naver Client ID/Secret이 비어 있으면 공식 프로필 API 호출이 불가능하므로 요청을 거부합니다.
     */
    private void ensureNaverClientConfigured() {
        if (!StringUtils.hasText(oauthProperties.naver().clientId()) || !StringUtils.hasText(oauthProperties.naver().clientSecret())) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "Naver OAuth Client ID 또는 Secret이 설정되어 있지 않습니다.");
        }
    }

    /**
     * 필수 문자열 요청값을 확인합니다.
     *
     * @param value 확인할 문자열입니다.
     * @param message 비어 있을 때 내려줄 오류 메시지입니다.
     */
    private void ensureText(String value, String message) {
        if (!StringUtils.hasText(value)) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, message);
        }
    }

    /**
     * Naver 프로필 응답의 Object 값을 문자열로 안전하게 변환합니다.
     *
     * @param value Naver 응답 Map에서 꺼낸 값입니다.
     * @return null 또는 문자열 값입니다.
     */
    private String asString(Object value) {
        return value == null ? null : String.valueOf(value);
    }

    /**
     * Naver access token 발급 API 응답 구조입니다.
     *
     * @param accessToken 프로필 조회에 사용할 access token입니다.
     * @param refreshToken Naver access token 갱신용 refresh token입니다.
     * @param tokenType token type입니다.
     * @param expiresIn access token 유효 시간(초)입니다.
     * @param error 실패 시 Naver가 내려주는 오류 코드입니다.
     * @param errorDescription 실패 시 Naver가 내려주는 오류 설명입니다.
     */
    private record NaverTokenResponse(
        @JsonProperty("access_token")
        String accessToken,

        @JsonProperty("refresh_token")
        String refreshToken,

        @JsonProperty("token_type")
        String tokenType,

        @JsonProperty("expires_in")
        Long expiresIn,

        String error,

        @JsonProperty("error_description")
        String errorDescription
    ) {
    }

    /**
     * Naver 회원 프로필 조회 API의 최상위 응답 구조입니다.
     *
     * @param resultcode 성공 시 "00"인 결과 코드입니다.
     * @param message 결과 메시지입니다.
     * @param response 사용자 프로필 데이터 Map입니다.
     */
    private record NaverProfileResponse(
        String resultcode,
        String message,
        Map<String, Object> response
    ) {
    }
}
