package com.sagopalgo.api.auth.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.auth.dto.AuthTokenResponse;
import com.sagopalgo.api.auth.dto.NaverLoginRequest;
import com.sagopalgo.api.auth.dto.RefreshTokenRequest;
import com.sagopalgo.api.auth.dto.SocialLoginRequest;
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
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

/**
 * AuthService의 핵심 인증 흐름을 DB 없이 검증하는 단위 테스트입니다.
 *
 * <p>소셜 OAuth 클라이언트, Mapper, 토큰 서비스는 Mockito로 대체해서, 테스트가 외부 Google/Naver,
 * MySQL 서버, 실제 JWT 서명에 의존하지 않고 서비스의 판단 로직만 빠르게 검증하도록 구성했습니다.</p>
 */
@ExtendWith(MockitoExtension.class)
class AuthServiceTest {

    @Mock
    private UserMapper userMapper;

    @Mock
    private GoogleOAuthClient googleOAuthClient;

    @Mock
    private NaverOAuthClient naverOAuthClient;

    @Mock
    private JwtTokenProvider jwtTokenProvider;

    @Mock
    private RefreshTokenService refreshTokenService;

    private AuthService authService;

    /**
     * 각 테스트마다 새로운 AuthService를 만들어 테스트 간 상태 공유를 없앱니다.
     */
    @BeforeEach
    void setUp() {
        authService = new AuthService(userMapper, googleOAuthClient, naverOAuthClient, jwtTokenProvider, refreshTokenService);
    }

    @Test
    @DisplayName("Google 로그인은 처음 보는 Google 사용자를 자동 생성하고 토큰 쌍을 발급한다")
    void googleLoginCreatesUserWhenSocialAccountIsNew() {
        SocialLoginRequest request = new SocialLoginRequest("google-id-token");
        OAuthUserProfile profile = googleProfile();
        Instant refreshExpiresAt = Instant.parse("2026-09-21T00:00:00Z");

        when(googleOAuthClient.fetchProfile(request.providerToken())).thenReturn(profile);
        when(userMapper.findByProviderAndProviderUserId("GOOGLE", "google-sub-1")).thenReturn(Optional.empty());
        doAnswer(invocation -> {
            User user = invocation.getArgument(0);
            user.setUserId(1L);
            return 1;
        }).when(userMapper).insert(any(User.class));
        when(jwtTokenProvider.createAccessToken(any(User.class))).thenReturn("access-token");
        when(jwtTokenProvider.createRefreshToken(any(User.class))).thenReturn("refresh-token");
        when(jwtTokenProvider.accessTokenExpiresInSeconds()).thenReturn(3600L);
        when(jwtTokenProvider.refreshTokenExpiresAt()).thenReturn(refreshExpiresAt);

        AuthTokenResponse response = authService.loginWithGoogle(request);

        assertThat(response.accessToken()).isEqualTo("access-token");
        assertThat(response.refreshToken()).isEqualTo("refresh-token");
        assertThat(response.user().authProvider()).isEqualTo("GOOGLE");
        assertThat(response.user().email()).isEqualTo("google@example.com");
        verify(refreshTokenService).save(1L, "refresh-token", refreshExpiresAt);
    }

    @Test
    @DisplayName("Naver 로그인은 기존 Naver 사용자의 프로필을 갱신하고 토큰 쌍을 발급한다")
    void naverLoginUpdatesExistingUserProfile() {
        NaverLoginRequest request = new NaverLoginRequest(
            "naver-authorization-code",
            "naver-state"
        );
        OAuthUserProfile profile = naverProfile();
        User existingUser = socialUser(OAuthProvider.NAVER, "naver-id-1");
        Instant refreshExpiresAt = Instant.parse("2026-09-21T00:00:00Z");

        when(naverOAuthClient.fetchProfile(
            request.authorizationCode(),
            request.state()
        )).thenReturn(profile);
        when(userMapper.findByProviderAndProviderUserId("NAVER", "naver-id-1")).thenReturn(Optional.of(existingUser));
        when(jwtTokenProvider.createAccessToken(existingUser)).thenReturn("access-token");
        when(jwtTokenProvider.createRefreshToken(existingUser)).thenReturn("refresh-token");
        when(jwtTokenProvider.accessTokenExpiresInSeconds()).thenReturn(3600L);
        when(jwtTokenProvider.refreshTokenExpiresAt()).thenReturn(refreshExpiresAt);

        AuthTokenResponse response = authService.loginWithNaver(request);

        assertThat(response.user().authProvider()).isEqualTo("NAVER");
        assertThat(response.user().nickname()).isEqualTo("네이버사용자");
        verify(userMapper).updateSocialProfile(existingUser);
        verify(refreshTokenService).save(1L, "refresh-token", refreshExpiresAt);
    }

    @Test
    @DisplayName("토큰 재발급은 저장된 refresh token을 폐기하고 새 토큰 쌍을 발급한다")
    void refreshRotatesRefreshTokenAndReturnsNewTokenPair() {
        RefreshTokenRequest request = new RefreshTokenRequest("old-refresh-token");
        RefreshToken savedRefreshToken = activeRefreshToken();
        User user = socialUser(OAuthProvider.GOOGLE, "google-sub-1");
        Instant refreshExpiresAt = Instant.parse("2026-09-21T00:00:00Z");

        when(jwtTokenProvider.parseRefreshTokenSubject(request.refreshToken())).thenReturn(1L);
        when(refreshTokenService.findActive(request.refreshToken())).thenReturn(Optional.of(savedRefreshToken));
        when(refreshTokenService.isExpired(savedRefreshToken)).thenReturn(false);
        when(userMapper.findById(1L)).thenReturn(Optional.of(user));
        when(jwtTokenProvider.createAccessToken(user)).thenReturn("new-access-token");
        when(jwtTokenProvider.createRefreshToken(user)).thenReturn("new-refresh-token");
        when(jwtTokenProvider.accessTokenExpiresInSeconds()).thenReturn(3600L);
        when(jwtTokenProvider.refreshTokenExpiresAt()).thenReturn(refreshExpiresAt);

        AuthTokenResponse response = authService.refresh(request);

        assertThat(response.accessToken()).isEqualTo("new-access-token");
        assertThat(response.refreshToken()).isEqualTo("new-refresh-token");
        assertThat(response.expiresIn()).isEqualTo(3600L);
        assertThat(response.user().userId()).isEqualTo(1L);
        verify(refreshTokenService).revoke(10L);
        verify(refreshTokenService).save(1L, "new-refresh-token", refreshExpiresAt);
    }

    @Test
    @DisplayName("토큰 재발급은 만료된 refresh token이면 폐기 후 인증 오류를 던진다")
    void refreshRejectsExpiredRefreshToken() {
        RefreshTokenRequest request = new RefreshTokenRequest("expired-refresh-token");
        RefreshToken savedRefreshToken = activeRefreshToken();

        when(jwtTokenProvider.parseRefreshTokenSubject(request.refreshToken())).thenReturn(1L);
        when(refreshTokenService.findActive(request.refreshToken())).thenReturn(Optional.of(savedRefreshToken));
        when(refreshTokenService.isExpired(savedRefreshToken)).thenReturn(true);

        assertThatThrownBy(() -> authService.refresh(request))
            .isInstanceOf(ApiException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.AUTH_INVALID_TOKEN);

        verify(refreshTokenService).revoke(10L);
    }

    @Test
    @DisplayName("로그아웃은 현재 사용자의 활성 refresh token을 모두 폐기한다")
    void logoutRevokesAllRefreshTokensForUser() {
        authService.logout(1L);

        verify(refreshTokenService).revokeAllByUserId(1L);
    }

    /**
     * 여러 테스트에서 재사용할 정상 상태 사용자 모델을 만듭니다.
     *
     * @param provider 소셜 로그인 제공자입니다.
     * @param providerUserId 제공자 사용자 고유 ID입니다.
     * @return 로그인 가능한 사용자 모델입니다.
     */
    private User socialUser(OAuthProvider provider, String providerUserId) {
        User user = new User();
        user.setUserId(1L);
        user.setAuthProvider(provider.name());
        user.setProviderUserId(providerUserId);
        user.setEmail("user@example.com");
        user.setNickname("투자초보");
        user.setProfileImageUrl("https://example.com/profile.png");
        user.setRole("USER");
        user.setStatus("ACTIVE");
        return user;
    }

    /**
     * Google OAuth 클라이언트가 반환할 검증된 사용자 프로필을 만듭니다.
     *
     * @return Google 소셜 로그인 프로필입니다.
     */
    private OAuthUserProfile googleProfile() {
        return new OAuthUserProfile(
            OAuthProvider.GOOGLE,
            "google-sub-1",
            "google@example.com",
            "구글사용자",
            "https://example.com/google.png"
        );
    }

    /**
     * Naver OAuth 클라이언트가 반환할 검증된 사용자 프로필을 만듭니다.
     *
     * @return Naver 소셜 로그인 프로필입니다.
     */
    private OAuthUserProfile naverProfile() {
        return new OAuthUserProfile(
            OAuthProvider.NAVER,
            "naver-id-1",
            "naver@example.com",
            "네이버사용자",
            "https://example.com/naver.png"
        );
    }

    /**
     * 재발급 테스트에서 사용할 활성 refresh token 모델을 만듭니다.
     *
     * @return 아직 폐기되지 않은 refresh token 모델입니다.
     */
    private RefreshToken activeRefreshToken() {
        RefreshToken refreshToken = new RefreshToken();
        refreshToken.setRefreshTokenId(10L);
        refreshToken.setUserId(1L);
        refreshToken.setTokenHash("hashed-token");
        refreshToken.setExpiresAt(LocalDateTime.parse("2026-09-21T00:00:00"));
        return refreshToken;
    }
}
