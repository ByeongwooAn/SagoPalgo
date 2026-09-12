package com.sagopalgo.api.kb.dto;

/**
 * KB증권 계좌 목록의 단일 계좌 응답입니다.
 */
public record KbAccountResponse(
    String provider,
    String accountAlias,
    String maskedAccountNumber,
    String accountProductCode,
    String accountName,
    String accountType,
    String currency
) {
}
