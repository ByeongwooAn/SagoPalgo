package com.sagopalgo.api.oauth.client;

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

/**
 * Naver 공식 프로필 조회 API로 access token을 검증하는 클라이언트입니다.
 *
 * <p>Naver 문서 기준으로 access token을 Authorization Bearer 헤더에 담고, 응답의 response.id 값을
 * 사고팔고의 provider_user_id로 사용합니다.</p>
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
     * Naver access token으로 프로필 API를 호출하고 내부 사용자 프로필로 변환합니다.
     *
     * @param providerToken Flutter 앱이 Naver 로그인 SDK에서 받은 access token입니다.
     * @return 검증된 Naver 사용자 프로필입니다.
     */
    @Override
    public OAuthUserProfile fetchProfile(String providerToken) {
        ensureNaverClientConfigured();

        NaverProfileResponse profileResponse;
        try {
            profileResponse = restClient.get()
                .uri(oauthProperties.naver().profileUri())
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + providerToken)
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
     * Naver Client ID/Secret이 비어 있으면 공식 프로필 API 호출이 불가능하므로 요청을 거부합니다.
     */
    private void ensureNaverClientConfigured() {
        if (!StringUtils.hasText(oauthProperties.naver().clientId()) || !StringUtils.hasText(oauthProperties.naver().clientSecret())) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "Naver OAuth Client ID 또는 Secret이 설정되어 있지 않습니다.");
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
