package com.sagopalgo.api.auth.service;

import com.sagopalgo.api.auth.dto.AuthTokenResponse;
import com.sagopalgo.api.auth.dto.RefreshTokenRequest;
import com.sagopalgo.api.auth.dto.SocialLoginRequest;
import com.sagopalgo.api.auth.dto.UserResponse;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.oauth.OAuthProvider;
import com.sagopalgo.api.oauth.client.GoogleOAuthClient;
import com.sagopalgo.api.oauth.client.NaverOAuthClient;
import com.sagopalgo.api.oauth.dto.OAuthUserProfile;
import com.sagopalgo.api.token.model.RefreshToken;
import com.sagopalgo.api.token.service.JwtTokenProvider;
import com.sagopalgo.api.token.service.RefreshTokenService;
import com.sagopalgo.api.user.mapper.UserMapper;
import com.sagopalgo.api.user.model.User;
import io.jsonwebtoken.JwtException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * Google/Naver 소셜 로그인과 JWT 재발급/로그아웃 비즈니스 로직을 담당하는 서비스입니다.
 *
 * <p>컨트롤러는 HTTP 요청/응답 변환만 담당하고, 외부 소셜 토큰 검증, 사용자 자동 생성/갱신,
 * 토큰 발급 같은 실제 인증 규칙은 이 서비스에 모아둡니다.</p>
 */
@Service
public class AuthService {

    private final UserMapper userMapper;
    private final GoogleOAuthClient googleOAuthClient;
    private final NaverOAuthClient naverOAuthClient;
    private final JwtTokenProvider jwtTokenProvider;
    private final RefreshTokenService refreshTokenService;

    /**
     * 인증 로직에 필요한 협력 객체들을 생성자 주입으로 받습니다.
     *
     * @param userMapper users 테이블 접근 Mapper입니다.
     * @param googleOAuthClient Google ID token 검증 클라이언트입니다.
     * @param naverOAuthClient Naver access token 검증 클라이언트입니다.
     * @param jwtTokenProvider JWT 생성 컴포넌트입니다.
     * @param refreshTokenService refresh token 저장 서비스입니다.
     */
    public AuthService(
        UserMapper userMapper,
        GoogleOAuthClient googleOAuthClient,
        NaverOAuthClient naverOAuthClient,
        JwtTokenProvider jwtTokenProvider,
        RefreshTokenService refreshTokenService
    ) {
        this.userMapper = userMapper;
        this.googleOAuthClient = googleOAuthClient;
        this.naverOAuthClient = naverOAuthClient;
        this.jwtTokenProvider = jwtTokenProvider;
        this.refreshTokenService = refreshTokenService;
    }

    /**
     * Google ID token을 검증하고 사고팔고 JWT 토큰 쌍을 발급합니다.
     *
     * @param request Google ID token을 담은 요청 DTO입니다.
     * @return 앱에서 사용할 사고팔고 access token과 refresh token입니다.
     */
    @Transactional
    public AuthTokenResponse loginWithGoogle(SocialLoginRequest request) {
        OAuthUserProfile profile = googleOAuthClient.fetchProfile(request.providerToken());
        User user = findOrCreateSocialUser(profile);
        return issueTokenPair(user);
    }

    /**
     * Naver access token을 검증하고 사고팔고 JWT 토큰 쌍을 발급합니다.
     *
     * @param request Naver access token을 담은 요청 DTO입니다.
     * @return 앱에서 사용할 사고팔고 access token과 refresh token입니다.
     */
    @Transactional
    public AuthTokenResponse loginWithNaver(SocialLoginRequest request) {
        OAuthUserProfile profile = naverOAuthClient.fetchProfile(request.providerToken());
        User user = findOrCreateSocialUser(profile);
        return issueTokenPair(user);
    }

    /**
     * refresh token을 검증하고 기존 token을 폐기한 뒤 새 token 쌍을 재발급합니다.
     *
     * <p>refresh token을 재사용 가능한 고정 토큰으로 두면 탈취 시 위험이 커지므로, 재발급할 때마다
     * 기존 refresh token은 revoked_at을 채우고 새 refresh token을 저장하는 회전 방식으로 처리합니다.</p>
     *
     * @param request refresh token 재발급 요청 DTO입니다.
     * @return 새 access token과 refresh token 응답입니다.
     */
    @Transactional
    public AuthTokenResponse refresh(RefreshTokenRequest request) {
        Long userId = parseRefreshTokenSubject(request.refreshToken());

        RefreshToken savedRefreshToken = refreshTokenService.findActive(request.refreshToken())
            .orElseThrow(() -> new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "이미 폐기되었거나 존재하지 않는 refresh token입니다."));

        if (!savedRefreshToken.getUserId().equals(userId)) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "refresh token 사용자 정보가 일치하지 않습니다.");
        }

        if (refreshTokenService.isExpired(savedRefreshToken)) {
            refreshTokenService.revoke(savedRefreshToken.getRefreshTokenId());
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "refresh token이 만료되었습니다.");
        }

        User user = userMapper.findById(userId)
            .orElseThrow(() -> new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "refresh token의 사용자를 찾을 수 없습니다."));

        refreshTokenService.revoke(savedRefreshToken.getRefreshTokenId());

        return issueTokenPair(user);
    }

    /**
     * 현재 로그인한 사용자의 활성 refresh token을 모두 폐기합니다.
     *
     * @param userId Authorization access token에서 확인한 사용자 ID입니다.
     */
    @Transactional
    public void logout(Long userId) {
        refreshTokenService.revokeAllByUserId(userId);
    }

    /**
     * 사용자 모델을 기준으로 access token과 refresh token을 발급하고 refresh token은 DB에 저장합니다.
     *
     * @param user 토큰을 발급할 사용자입니다.
     * @return 앱에 내려줄 토큰 응답 DTO입니다.
     */
    private AuthTokenResponse issueTokenPair(User user) {
        String accessToken = jwtTokenProvider.createAccessToken(user);
        String refreshToken = jwtTokenProvider.createRefreshToken(user);

        refreshTokenService.save(user.getUserId(), refreshToken, jwtTokenProvider.refreshTokenExpiresAt());

        return new AuthTokenResponse(
            accessToken,
            refreshToken,
            jwtTokenProvider.accessTokenExpiresInSeconds(),
            UserResponse.from(user)
        );
    }

    /**
     * 소셜 제공자 고유 ID로 기존 사용자를 찾고, 없으면 새 사용자를 생성합니다.
     *
     * <p>Google 공식 문서의 sub, Naver 공식 문서의 response.id처럼 제공자별 고유 식별자를 기준으로
     * 사용자를 매칭합니다. 이메일은 변경될 수 있으므로 로그인 식별 키로 사용하지 않습니다.</p>
     *
     * @param profile 외부 제공자에서 검증된 사용자 프로필입니다.
     * @return 기존 또는 새로 생성된 사고팔고 사용자입니다.
     */
    private User findOrCreateSocialUser(OAuthUserProfile profile) {
        return userMapper
            .findByProviderAndProviderUserId(profile.provider().name(), profile.providerUserId())
            .map(existingUser -> updateSocialProfile(existingUser, profile))
            .orElseGet(() -> createSocialUser(profile));
    }

    /**
     * 기존 사용자의 소셜 프로필 정보를 최신 값으로 갱신합니다.
     *
     * @param user DB에서 조회한 기존 사용자입니다.
     * @param profile 외부 제공자에서 받은 최신 프로필입니다.
     * @return 갱신된 사용자 모델입니다.
     */
    private User updateSocialProfile(User user, OAuthUserProfile profile) {
        user.setEmail(profile.email());
        user.setNickname(resolveNickname(profile));
        user.setProfileImageUrl(profile.profileImageUrl());
        userMapper.updateSocialProfile(user);
        return user;
    }

    /**
     * 처음 로그인한 소셜 사용자를 users 테이블에 등록합니다.
     *
     * @param profile 외부 제공자에서 받은 검증된 프로필입니다.
     * @return DB에 저장된 신규 사용자 모델입니다.
     */
    private User createSocialUser(OAuthUserProfile profile) {
        User user = new User();
        user.setAuthProvider(profile.provider().name());
        user.setProviderUserId(profile.providerUserId());
        user.setEmail(profile.email());
        user.setNickname(resolveNickname(profile));
        user.setProfileImageUrl(profile.profileImageUrl());
        user.setRole("USER");
        user.setStatus("ACTIVE");

        userMapper.insert(user);

        return user;
    }

    /**
     * 제공자가 닉네임을 내려주지 않는 경우 앱에서 표시 가능한 기본 닉네임을 만듭니다.
     *
     * @param profile 외부 제공자 프로필입니다.
     * @return 화면 표시용 닉네임입니다.
     */
    private String resolveNickname(OAuthUserProfile profile) {
        if (profile.nickname() != null && !profile.nickname().isBlank()) {
            return profile.nickname();
        }

        return profile.provider() == OAuthProvider.GOOGLE ? "Google 사용자" : "Naver 사용자";
    }

    /**
     * refresh token 문자열을 파싱해 사용자 ID를 추출하고, 실패하면 API 예외로 변환합니다.
     *
     * @param refreshToken 클라이언트가 보낸 refresh token 원문입니다.
     * @return refresh token subject에 담긴 사용자 ID입니다.
     */
    private Long parseRefreshTokenSubject(String refreshToken) {
        try {
            return jwtTokenProvider.parseRefreshTokenSubject(refreshToken);
        } catch (JwtException | IllegalArgumentException exception) {
            throw new ApiException(ErrorCode.AUTH_INVALID_TOKEN, "refresh token이 유효하지 않습니다.");
        }
    }
}
