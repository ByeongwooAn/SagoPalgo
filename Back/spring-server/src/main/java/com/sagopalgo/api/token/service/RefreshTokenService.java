package com.sagopalgo.api.token.service;

import com.sagopalgo.api.token.mapper.RefreshTokenMapper;
import com.sagopalgo.api.token.model.RefreshToken;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Base64;
import java.util.Optional;
import org.springframework.stereotype.Service;

/**
 * refresh token 저장과 해시 처리를 담당하는 서비스입니다.
 *
 * <p>토큰 생성은 JwtTokenProvider가 담당하고, 이 서비스는 저장 전 해싱, 활성 토큰 확인,
 * 토큰 폐기처럼 DB 보관 정책과 관련된 책임만 갖도록 분리했습니다.</p>
 */
@Service
public class RefreshTokenService {

    private final RefreshTokenMapper refreshTokenMapper;

    /**
     * refresh token 저장 Mapper를 주입받습니다.
     *
     * @param refreshTokenMapper refresh_tokens 테이블 접근 Mapper입니다.
     */
    public RefreshTokenService(RefreshTokenMapper refreshTokenMapper) {
        this.refreshTokenMapper = refreshTokenMapper;
    }

    /**
     * refresh token 원문을 해시로 변환한 뒤 DB에 저장합니다.
     *
     * @param userId refresh token 소유 사용자 ID입니다.
     * @param refreshToken 사용자에게 발급한 refresh token 원문입니다.
     * @param expiresAt refresh token 만료 시각입니다.
     */
    public void save(Long userId, String refreshToken, java.time.Instant expiresAt) {
        RefreshToken token = new RefreshToken();
        token.setUserId(userId);
        token.setTokenHash(hashToken(refreshToken));
        token.setExpiresAt(LocalDateTime.ofInstant(expiresAt, ZoneOffset.UTC));

        refreshTokenMapper.insert(token);
    }

    /**
     * refresh token 원문과 일치하는 활성 DB 토큰을 찾습니다.
     *
     * @param refreshToken 클라이언트가 보낸 refresh token 원문입니다.
     * @return 아직 폐기되지 않은 refresh token이 있으면 Optional에 담아 반환합니다.
     */
    public Optional<RefreshToken> findActive(String refreshToken) {
        return refreshTokenMapper.findActiveByTokenHash(hashToken(refreshToken));
    }

    /**
     * refresh token 만료 여부를 UTC 기준으로 확인합니다.
     *
     * @param refreshToken DB에서 조회한 refresh token 모델입니다.
     * @return 만료 시간이 현재 UTC 시각보다 이전이면 true입니다.
     */
    public boolean isExpired(RefreshToken refreshToken) {
        return refreshToken.getExpiresAt().isBefore(LocalDateTime.now(ZoneOffset.UTC));
    }

    /**
     * 특정 refresh token을 폐기 처리합니다.
     *
     * @param refreshTokenId 폐기할 refresh token PK입니다.
     */
    public void revoke(Long refreshTokenId) {
        refreshTokenMapper.revokeById(refreshTokenId);
    }

    /**
     * 특정 사용자의 모든 활성 refresh token을 폐기 처리합니다.
     *
     * @param userId 로그아웃한 사용자 ID입니다.
     */
    public void revokeAllByUserId(Long userId) {
        refreshTokenMapper.revokeAllByUserId(userId);
    }

    /**
     * SHA-256으로 토큰 원문을 해시하고 Base64 문자열로 변환합니다.
     *
     * @param token 해시 처리할 refresh token 원문입니다.
     * @return DB에 저장할 Base64 인코딩 해시입니다.
     */
    private String hashToken(String token) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hashed = digest.digest(token.getBytes(StandardCharsets.UTF_8));
            return Base64.getEncoder().encodeToString(hashed);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 알고리즘을 사용할 수 없습니다.", exception);
        }
    }
}
