package com.sagopalgo.api.kb.dto;

import java.util.List;

/**
 * KB증권 계좌 목록 조회 응답입니다.
 */
public record KbAccountListResponse(
    List<KbAccountResponse> items
) {
}
