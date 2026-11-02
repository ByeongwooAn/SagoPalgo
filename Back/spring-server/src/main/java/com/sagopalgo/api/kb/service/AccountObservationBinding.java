package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.util.HexFormat;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.stereotype.Component;

/** 주문용 지문과 분리된 읽기 이력 namespace. B2C의 선택적 계좌번호를 강제하지 않습니다. */
@Component
public class AccountObservationBinding {
    private final SecuritiesProviderProperties properties;

    public AccountObservationBinding(SecuritiesProviderProperties properties) {
        this.properties = properties;
    }

    public String current() {
        var kb = properties.getKb();
        if (!kb.hasRequiredSecrets() || blank(kb.getBaseUrl()) || blank(kb.getTokenPath())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "계좌 관찰 이력을 구분할 KB 연결·인증 설정이 필요합니다.");
        }
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(kb.getAppSecret().getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            for (String value : List.of("KB_ACCOUNT_OBSERVATION_V1", kb.getBaseUrl(), kb.getTokenPath(),
                kb.getAppKey(), safe(kb.getAccountNumber()), safe(kb.getAccountProductCode()))) {
                byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
                mac.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
                mac.update(bytes);
            }
            return HexFormat.of().formatHex(mac.doFinal());
        } catch (GeneralSecurityException exception) {
            throw new IllegalStateException("계좌 관찰 연결 식별값을 만들 수 없습니다.");
        }
    }

    public boolean matches(String captured) {
        try { return current().equals(captured); }
        catch (ApiException exception) { return false; }
    }

    private boolean blank(String value) { return value == null || value.isBlank(); }
    private String safe(String value) { return value == null ? "" : value; }
}
