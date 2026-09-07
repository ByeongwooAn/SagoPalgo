package com.sagopalgo.api.user.mapper;

import com.sagopalgo.api.user.model.User;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * users 테이블에 접근하는 MyBatis Mapper입니다.
 *
 * <p>이메일/비밀번호 로그인을 제거했기 때문에 사용자는 auth_provider와 provider_user_id 조합으로
 * 찾습니다. 쿼리가 복잡해지는 추천/포트폴리오 기능부터 XML Mapper로 분리하면 됩니다.</p>
 */
@Mapper
public interface UserMapper {

    /**
     * 소셜 로그인 제공자와 제공자 사용자 ID로 기존 사용자를 조회합니다.
     *
     * @param authProvider GOOGLE 또는 NAVER 같은 로그인 제공자입니다.
     * @param providerUserId 제공자가 보장하는 사용자 고유 ID입니다.
     * @return 일치하는 사용자가 있으면 User를 담고, 없으면 빈 Optional을 반환합니다.
     */
    @Select("""
        SELECT user_id, auth_provider, provider_user_id, email, nickname, profile_image_url, role, status, created_at, updated_at
        FROM users
        WHERE auth_provider = #{authProvider}
          AND provider_user_id = #{providerUserId}
        """)
    Optional<User> findByProviderAndProviderUserId(
        @Param("authProvider") String authProvider,
        @Param("providerUserId") String providerUserId
    );

    /**
     * JWT subject에 들어 있는 사용자 ID로 현재 사용자를 조회합니다.
     *
     * @param userId 조회할 사용자 PK입니다.
     * @return 사용자가 존재하면 User를 담고, 없으면 빈 Optional을 반환합니다.
     */
    @Select("""
        SELECT user_id, auth_provider, provider_user_id, email, nickname, profile_image_url, role, status, created_at, updated_at
        FROM users
        WHERE user_id = #{userId}
        """)
    Optional<User> findById(@Param("userId") Long userId);

    /**
     * 새 소셜 로그인 사용자를 users 테이블에 저장합니다.
     *
     * @param user 소셜 제공자 프로필에서 만든 사용자 모델입니다.
     * @return 삽입된 행 수입니다.
     */
    @Insert("""
        INSERT INTO users (auth_provider, provider_user_id, email, nickname, profile_image_url, role, status)
        VALUES (#{authProvider}, #{providerUserId}, #{email}, #{nickname}, #{profileImageUrl}, #{role}, #{status})
        """)
    @Options(useGeneratedKeys = true, keyProperty = "userId", keyColumn = "user_id")
    int insert(User user);

    /**
     * 로그인할 때마다 제공자 프로필의 최신 이메일/닉네임/이미지 정보를 반영합니다.
     *
     * @param user 최신 소셜 프로필을 담은 사용자 모델입니다.
     * @return 수정된 행 수입니다.
     */
    @Update("""
        UPDATE users
        SET email = #{email},
            nickname = #{nickname},
            profile_image_url = #{profileImageUrl}
        WHERE user_id = #{userId}
        """)
    int updateSocialProfile(User user);
}
