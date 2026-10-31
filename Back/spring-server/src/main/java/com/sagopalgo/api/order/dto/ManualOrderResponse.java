package com.sagopalgo.api.order.dto;

import com.sagopalgo.api.order.model.ManualOrderCommand;
import java.math.BigDecimal;
import java.time.LocalDateTime;

public record ManualOrderResponse(
    String commandId, Long approvalId, String parentId, String kind, String stockCode, String stockName,
    String market, String side, BigDecimal price, BigDecimal quantity, String status,
    String orderNo, String orderDate, String resultCode, String processCode, boolean changeUsed,
    LocalDateTime createdAt, String message, ManualOrderReconciliationResponse reconciliation
) {
    public static ManualOrderResponse from(ManualOrderCommand c) {
        return from(c, null);
    }

    public static ManualOrderResponse from(ManualOrderCommand c,
        com.sagopalgo.api.order.model.ManualOrderReconciliationRecord reconciliation) {
        String message = switch (c.status()) {
            case "ACCEPTED" -> "KB 접수 응답을 받았습니다. 체결 완료 여부는 체결 조회로 확인하세요.";
            case "REJECTED" -> "KB 거절 응답을 받았습니다. 같은 요청은 재전송하지 않습니다.";
            case "PREPARED" -> "90초 이내에 주문안을 다시 확인하세요. 아직 전송하지 않았습니다.";
            default -> "접수 여부를 확정할 수 없습니다. 재전송하지 말고 KB 앱에서 확인하세요.";
        };
        return new ManualOrderResponse(c.commandId(), c.approvalId(), c.parentId(), c.kind(), c.stockCode(),
            c.stockName(), c.market(), c.side(), c.price(), c.quantity(), c.status(), c.orderNo(), c.orderDate(),
            c.resultCode(), c.processCode(), c.changeId() != null, c.createdAt(), message,
            ManualOrderReconciliationResponse.from(reconciliation));
    }
}
