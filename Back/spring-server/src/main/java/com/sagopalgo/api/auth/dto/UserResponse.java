package com.sagopalgo.api.auth.dto;

import com.sagopalgo.api.user.model.User;

/**
 * 인증 API 응답에서 사용자 기본 정보를 내려줄 때 사용하는 DTO입니다.
 *
 * <p>provider_user_id, 계정 상태 같은 내부 필드는 절대 클라이언트에 노출하지 않고,
 * 앱 화면에 필요한 최소 정보만 포함합니다.</p>
 *
 * @param userId 사용자 고유 ID입니다.
 * @param authProvider 로그인 제공자입니다.
 * @param email 로그인 이메일입니다.
 * @param nickname 앱 표시 닉네임입니다.
 * @param profileImageUrl 프로필 이미지 URL입니다.
 */
public record UserResponse(
    Long userId,
    String authProvider,
    String email,
    String nickname,
    String profileImageUrl
) {

    /**
     * DB 모델을 API 응답 DTO로 변환합니다.
     *
     * @param user users 테이블에서 조회된 사용자 모델입니다.
     * @return 클라이언트에 내려줄 사용자 응답 DTO입니다.
     */
    public static UserResponse from(User user) {
        return new UserResponse(
            user.getUserId(),
            user.getAuthProvider(),
            user.getEmail(),
            user.getNickname(),
            user.getProfileImageUrl()
        );
    }
}
