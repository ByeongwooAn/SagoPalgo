package com.sagopalgo.api.user.mapper;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;

/**
 * 개인용 로컬 사용자 행을 준비하는 MyBatis Mapper입니다.
 */
@Mapper
public interface UserMapper {

    /**
     * 개인용 모드에서 사용할 로컬 소유자 행을 준비합니다.
     *
     * <p>이미 같은 user_id가 있으면 기존 데이터를 건드리지 않아, 과거 개발 데이터와 함께 사용할 수 있습니다.</p>
     *
     * @param userId 개인용 데이터 소유자로 사용할 사용자 PK입니다.
     * @param email 로컬 사용자 식별용 이메일입니다.
     * @param nickname 앱에 표시할 로컬 사용자 이름입니다.
     * @return 새로 삽입된 행 수입니다. 이미 있으면 0을 반환합니다.
     */
    @Insert("""
        INSERT IGNORE INTO users (
            user_id,
            auth_provider,
            provider_user_id,
            email,
            nickname,
            profile_image_url,
            role,
            status
        )
        VALUES (
            #{userId},
            'LOCAL',
            'personal-owner',
            #{email},
            #{nickname},
            NULL,
            'USER',
            'ACTIVE'
        )
        """)
    int ensureLocalOwner(
        @Param("userId") Long userId,
        @Param("email") String email,
        @Param("nickname") String nickname
    );
}
