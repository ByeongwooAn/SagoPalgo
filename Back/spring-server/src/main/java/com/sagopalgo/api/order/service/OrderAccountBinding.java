package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.InvalidKeyException;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** 승인 당시 KB 연결을 계좌번호 원문 없이 묶습니다. 설정 변경은 기존 승인을 무효화합니다. */
@Component
public class OrderAccountBinding {
    private final Provider kb;

    public OrderAccountBinding(SecuritiesProviderProperties properties) {
        this.kb = properties.getKb();
    }

    public String requireFingerprint() {
        String fingerprint = currentFingerprint();
        if (fingerprint == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB 계좌·인증 설정이 없어 주문 승인을 사용할 수 없습니다.");
        }
        return fingerprint;
    }

    public boolean matches(String storedFingerprint) {
        String current = currentFingerprint();
        return storedFingerprint != null && current != null && storedFingerprint.equals(current);
    }

    private String currentFingerprint() {
        if (!kb.hasRequiredSecrets() || !kb.hasAccountNumber()
            || kb.getBaseUrl() == null || kb.getBaseUrl().isBlank()) {
            return null;
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(kb.getAppSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            update(mac, kb.getBaseUrl());
            update(mac, kb.getAppKey());
            update(mac, kb.getAccountNumber());
            update(mac, kb.getAccountProductCode());
            return HexFormat.of().formatHex(mac.doFinal());
        } catch (NoSuchAlgorithmException | InvalidKeyException exception) {
            throw new IllegalStateException("KB 계좌 승인 지문을 만들 수 없습니다.", exception);
        }
    }

    private void update(Mac mac, String value) {
        byte[] bytes = (value == null ? "" : value).getBytes(StandardCharsets.UTF_8);
        mac.update(ByteBuffer.allocate(Integer.BYTES).putInt(bytes.length).array());
        mac.update(bytes);
    }
}
