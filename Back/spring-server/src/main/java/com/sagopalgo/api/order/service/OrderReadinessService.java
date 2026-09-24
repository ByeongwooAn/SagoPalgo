package com.sagopalgo.api.order.service;

import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.order.dto.OrderReadinessCheckResponse;
import com.sagopalgo.api.order.dto.OrderReadinessResponse;
import java.net.URI;
import java.util.List;
import org.springframework.stereotype.Service;

/** 설정 누락을 진단하지만 실제 주문 전송 권한을 부여하지 않습니다. */
@Service
public class OrderReadinessService {
    private final Provider kb;

    public OrderReadinessService(SecuritiesProviderProperties properties) {
        this.kb = properties.getKb();
    }

    public OrderReadinessResponse status() {
        return new OrderReadinessResponse(false, List.of(
            check("ACCOUNT_SWITCH", kb.isAccountEnabled(), "KB 계좌 조회가 활성화되어야 합니다."),
            check("ORDER_PRECHECK_SWITCH", kb.isOrderEnabled(), "KB 주문 사전검증 스위치가 꺼져 있습니다."),
            check("LIVE_ORDER_SWITCH", kb.isLiveOrderEnabled(), "실주문 별도 스위치가 꺼져 있습니다."),
            check("CREDENTIALS", kb.hasRequiredSecrets(), "KB App Key 또는 App Secret이 누락되었습니다."),
            check("ACCOUNT_NUMBER", kb.hasAccountNumber(), "KB 계좌번호가 누락되었습니다."),
            check("HTTPS_ENDPOINT", validHttpsEndpoint(kb.getBaseUrl()), "KB HTTPS 엔드포인트가 올바르지 않습니다."),
            check("ORDER_IP", validIp(kb.getOrderIpAddress()), "운영 주문 IP 주소가 누락되었거나 올바르지 않습니다."),
            check("ORDER_MAC", validMac(kb.getOrderMacAddress()), "운영 주문 MAC 주소가 누락되었거나 올바르지 않습니다."),
            check("SUBMISSION_TRANSPORT", false, "KB 실주문 전송 어댑터가 아직 연결되지 않았습니다.")
        ));
    }

    private OrderReadinessCheckResponse check(String code, boolean passed, String blocker) {
        return new OrderReadinessCheckResponse(code, passed, passed ? "설정됨" : blocker);
    }

    private boolean validHttpsEndpoint(String value) {
        if (value == null || value.isBlank()) {
            return false;
        }
        try {
            URI uri = URI.create(value);
            return "https".equalsIgnoreCase(uri.getScheme()) && uri.getHost() != null;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private boolean validIp(String value) {
        if (value == null) {
            return false;
        }
        String[] parts = value.split("\\.", -1);
        if (parts.length != 4) {
            return false;
        }
        int[] octets = new int[4];
        for (int index = 0; index < parts.length; index++) {
            if (!parts[index].matches("[0-9]{1,3}")) {
                return false;
            }
            octets[index] = Integer.parseInt(parts[index]);
            if (octets[index] > 255) {
                return false;
            }
        }
        return octets[0] > 0 && octets[0] < 224 && octets[0] != 127
            && !(octets[0] == 169 && octets[1] == 254);
    }

    private boolean validMac(String value) {
        if (value == null) {
            return false;
        }
        boolean colon = value.matches("(?i)([0-9a-f]{2}:){5}[0-9a-f]{2}");
        boolean hyphen = value.matches("(?i)([0-9a-f]{2}-){5}[0-9a-f]{2}");
        if (!colon && !hyphen) {
            return false;
        }
        String normalized = value.replace(":", "").replace("-", "");
        int firstOctet = Integer.parseInt(normalized.substring(0, 2), 16);
        return !normalized.matches("(?i)0{12}|f{12}") && (firstOctet & 1) == 0;
    }
}
