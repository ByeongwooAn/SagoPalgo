package com.sagopalgo.api.auth.controller;

import com.sagopalgo.api.auth.dto.AuthTokenResponse;
import com.sagopalgo.api.auth.dto.RefreshTokenRequest;
import com.sagopalgo.api.auth.dto.SocialLoginRequest;
import com.sagopalgo.api.auth.service.AuthService;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 인증 관련 HTTP API를 제공하는 컨트롤러입니다.
 *
 * <p>이메일/비밀번호 회원가입과 로그인을 제거하고, Google/Naver 소셜 로그인만 제공해 앱의
 * 기본 인증 흐름을 구성합니다.</p>
 */
@RestController
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService authService;

    /**
     * 인증 서비스 의존성을 주입받습니다.
     *
     * @param authService 회원가입/로그인 비즈니스 로직을 처리하는 서비스입니다.
     */
    public AuthController(AuthService authService) {
        this.authService = authService;
    }

    /**
     * Google ID token으로 로그인하고 사고팔고 JWT 토큰을 발급하는 API입니다.
     *
     * @param request Google 로그인 SDK에서 받은 ID token 요청입니다.
     * @return access token, refresh token, 사용자 기본 정보입니다.
     */
    @PostMapping("/google")
    public ResponseEntity<ApiResponse<AuthTokenResponse>> loginWithGoogle(@Valid @RequestBody SocialLoginRequest request) {
        AuthTokenResponse response = authService.loginWithGoogle(request);
        return ResponseEntity.ok(ApiResponse.success(response, "Google 로그인이 완료되었습니다."));
    }

    /**
     * Naver access token으로 로그인하고 사고팔고 JWT 토큰을 발급하는 API입니다.
     *
     * @param request Naver 로그인 SDK에서 받은 access token 요청입니다.
     * @return access token, refresh token, 사용자 기본 정보입니다.
     */
    @PostMapping("/naver")
    public ResponseEntity<ApiResponse<AuthTokenResponse>> loginWithNaver(@Valid @RequestBody SocialLoginRequest request) {
        AuthTokenResponse response = authService.loginWithNaver(request);
        return ResponseEntity.ok(ApiResponse.success(response, "Naver 로그인이 완료되었습니다."));
    }

    /**
     * refresh token으로 access token과 refresh token을 재발급하는 API입니다.
     *
     * @param request 기존 refresh token을 담은 요청입니다.
     * @return 새 access token, 새 refresh token, 사용자 기본 정보입니다.
     */
    @PostMapping("/refresh")
    public ResponseEntity<ApiResponse<AuthTokenResponse>> refresh(@Valid @RequestBody RefreshTokenRequest request) {
        AuthTokenResponse response = authService.refresh(request);
        return ResponseEntity.ok(ApiResponse.success(response, "토큰이 재발급되었습니다."));
    }

    /**
     * 현재 로그인한 사용자의 refresh token을 폐기하는 로그아웃 API입니다.
     *
     * @param authenticatedUser JWT 필터가 SecurityContext에 저장한 현재 사용자 정보입니다.
     * @return 본문 데이터 없이 로그아웃 성공 메시지만 내려줍니다.
     */
    @PostMapping("/logout")
    public ResponseEntity<ApiResponse<Void>> logout(@AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser) {
        authService.logout(authenticatedUser.userId());
        return ResponseEntity.ok(ApiResponse.success(null, "로그아웃되었습니다."));
    }
}
