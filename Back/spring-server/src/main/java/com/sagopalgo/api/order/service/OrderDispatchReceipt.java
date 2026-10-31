package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.client.KbLimitOrderContract;

/** 실주문/시뮬레이션 공통 반환 결과. 원문 메시지·키·계좌번호를 보관하지 않습니다. */
public record OrderDispatchReceipt(String status, String orderNo, String resultCode, String processCode) {
    public static OrderDispatchReceipt from(KbLimitOrderContract.Outcome outcome) {
        String status = outcome == null || outcome.status() == null ? "UNKNOWN" : outcome.status().name();
        String number = outcome == null || outcome.orderNumber() == null ? "" : outcome.orderNumber();
        if ("ACCEPTED".equals(status) && (!number.matches("[0-9]{10}") || number.matches("0+"))) status = "UNKNOWN";
        if (!"ACCEPTED".equals(status)) number = "";
        return new OrderDispatchReceipt(status, number, code(outcome == null ? null : outcome.resultCode()),
            code(outcome == null ? null : outcome.processCode()));
    }

    public boolean valid() {
        if (status == null || orderNo == null || resultCode == null || processCode == null) return false;
        try {
            return equals(from(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.valueOf(status), orderNo, resultCode, processCode, "")));
        } catch (IllegalArgumentException exception) { return false; }
    }

    public static void requireReplayable(String commandStatus, String phase, OrderDispatchReceipt receipt) {
        if (!"SENDING".equals(commandStatus) || !"RETURNED".equals(phase) || receipt == null || !receipt.valid()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,
                "종료된 전송의 저장 결과를 확인할 수 없습니다. 진행 중·기존 미확정 기록은 차단을 유지합니다.");
        }
    }

    private static String code(String value) { return value != null && value.matches("[A-Za-z0-9_-]{1,30}") ? value : ""; }
}
