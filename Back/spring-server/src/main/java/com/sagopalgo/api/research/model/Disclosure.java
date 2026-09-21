package com.sagopalgo.api.research.model;

import java.time.LocalDate;

/**
 * 전자공시 Provider 응답을 통일한 내부 모델입니다.
 */
public record Disclosure(
    String provider,
    String stockCode,
    String corpCode,
    String corpName,
    String reportName,
    String receiptNumber,
    String submitterName,
    LocalDate receiptDate,
    String link
) {
}
