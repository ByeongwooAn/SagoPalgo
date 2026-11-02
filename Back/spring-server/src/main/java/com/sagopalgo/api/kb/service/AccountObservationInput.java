package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import java.util.UUID;

final class AccountObservationInput {
    private AccountObservationInput() {}

    static String requestId(String value) {
        if (value == null || !value.matches("[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}")) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "저장 요청 ID는 UUID여야 합니다.");
        }
        return UUID.fromString(value).toString();
    }
}
