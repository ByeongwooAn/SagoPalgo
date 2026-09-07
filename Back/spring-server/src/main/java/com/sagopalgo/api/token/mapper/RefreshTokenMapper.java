package com.sagopalgo.api.token.mapper;

import com.sagopalgo.api.token.model.RefreshToken;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * refresh_tokens 테이블에 refresh token 해시를 저장하는 Mapper입니다.
 *
 * <p>로그인 시 저장, 재발급 시 단일 토큰 조회/폐기, 로그아웃 시 사용자 단위 폐기를 담당합니다.</p>
 */
@Mapper
public interface RefreshTokenMapper {

    /**
     * 발급된 refresh token의 해시와 만료 시각을 DB에 저장합니다.
     *
     * @param refreshToken 저장할 refresh token 모델입니다.
     * @return 삽입된 행 수입니다.
     */
    @Insert("""
        INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
        VALUES (#{userId}, #{tokenHash}, #{expiresAt})
        """)
    @Options(useGeneratedKeys = true, keyProperty = "refreshTokenId", keyColumn = "refresh_token_id")
    int insert(RefreshToken refreshToken);

    /**
     * refresh token 해시로 아직 폐기되지 않은 토큰을 조회합니다.
     *
     * @param tokenHash refresh token 원문을 SHA-256으로 해시한 값입니다.
     * @return 활성 토큰이 있으면 RefreshToken을 담고, 없으면 빈 Optional을 반환합니다.
     */
    @Select("""
        SELECT refresh_token_id, user_id, token_hash, expires_at, revoked_at, created_at
        FROM refresh_tokens
        WHERE token_hash = #{tokenHash}
          AND revoked_at IS NULL
        """)
    Optional<RefreshToken> findActiveByTokenHash(@Param("tokenHash") String tokenHash);

    /**
     * 특정 refresh token을 폐기 처리합니다.
     *
     * @param refreshTokenId 폐기할 refresh token PK입니다.
     * @return 수정된 행 수입니다.
     */
    @Update("""
        UPDATE refresh_tokens
        SET revoked_at = UTC_TIMESTAMP()
        WHERE refresh_token_id = #{refreshTokenId}
          AND revoked_at IS NULL
        """)
    int revokeById(@Param("refreshTokenId") Long refreshTokenId);

    /**
     * 특정 사용자의 활성 refresh token을 모두 폐기합니다.
     *
     * @param userId 로그아웃한 사용자 ID입니다.
     * @return 수정된 행 수입니다.
     */
    @Update("""
        UPDATE refresh_tokens
        SET revoked_at = UTC_TIMESTAMP()
        WHERE user_id = #{userId}
          AND revoked_at IS NULL
        """)
    int revokeAllByUserId(@Param("userId") Long userId);
}
