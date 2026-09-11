package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * 개인용 Windows 프로그램으로 실행할 때 사용할 로컬 사용자 설정입니다.
 *
 * @param enabled JWT 로그인 없이 로컬 사용자로 API를 사용할지 여부입니다.
 * @param userId 개인용 데이터 소유자로 사용할 users.user_id 값입니다.
 * @param nickname 화면과 로그에서 표시할 로컬 사용자 이름입니다.
 * @param email 로컬 사용자 식별용 이메일입니다.
 */
@ConfigurationProperties(prefix = "sagopalgo.personal")
public record PersonalModeProperties(
    boolean enabled,
    Long userId,
    String nickname,
    String email
) {
}
