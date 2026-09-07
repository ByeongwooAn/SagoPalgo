package com.sagopalgo.api.security;

/**
 * JWT 검증이 끝난 뒤 SecurityContext에 저장할 사용자 인증 정보입니다.
 *
 * <p>Spring Security의 principal로 사용되며, 컨트롤러에서는 @AuthenticationPrincipal로 이 값을
 * 받아 현재 로그인한 사용자 ID를 확인할 수 있습니다.</p>
 *
 * @param userId JWT subject에서 추출한 사용자 ID입니다.
 * @param email JWT 클레임에 담긴 이메일입니다.
 * @param nickname JWT 클레임에 담긴 닉네임입니다.
 * @param role JWT 클레임에 담긴 권한입니다.
 */
public record JwtAuthenticatedUser(
    Long userId,
    String email,
    String nickname,
    String role
) {
}
