package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;

/** 실주문과 주문 시뮬레이터가 공유하는 순수 검증 규칙입니다. 외부 API·DB에 접근하지 않습니다. */
public final class OrderWorkflowRules {
    public static final int APPROVAL_SECONDS = 90;
    private OrderWorkflowRules() {}

    public static String issueToken() {
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
    }

    public static String hash(String token) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(token.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }

    public static boolean validToken(String token, String hash, LocalDateTime expires, LocalDateTime now) {
        return token != null && token.length() <= 200 && hash != null && expires != null && expires.isAfter(now)
            && MessageDigest.isEqual(hash(token).getBytes(StandardCharsets.US_ASCII), hash.getBytes(StandardCharsets.US_ASCII));
    }

    public static BigDecimal deviation(BigDecimal price, BigDecimal quote) {
        if (quote == null || quote.signum() <= 0) return BigDecimal.ZERO;
        return price.subtract(quote).abs().divide(quote, 8, RoundingMode.HALF_UP).multiply(new BigDecimal("100"));
    }

    public static boolean covers(BigDecimal available, BigDecimal required) {
        return available != null && available.compareTo(required) >= 0;
    }

    public static void requireAmendedPrice(BigDecimal original, BigDecimal amended) {
        if (original == null || amended == null || amended.signum() <= 0 || original.compareTo(amended) == 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "새 지정가는 기존과 다른 양수 가격이어야 합니다.");
        }
    }

    /** 기존 예약금 반환을 가정하지 않고 새 주문 전체 금액을 별도 가용 현금으로 확인합니다. */
    public static boolean requiresAmendCash(String side, BigDecimal original, BigDecimal amended) {
        return "BUY".equals(side) && amended.compareTo(original) > 0;
    }

    public static void requireChangeable(String kind, String status, boolean changed, boolean sameDay) {
        if (!"NEW".equals(kind) || !"ACCEPTED".equals(status) || changed || !sameDay) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "당일 신규 접수 주문만 한 차례 전부 정정·취소할 수 있습니다.");
        }
    }
}
