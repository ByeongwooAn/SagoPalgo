package com.sagopalgo.api.research.model;

import java.time.LocalDate;

/**
 * 한 종목의 뉴스와 공시를 조회하기 위한 내부 요청입니다.
 */
public record ResearchRequest(
    String stockCode,
    String stockName,
    LocalDate fromDate,
    LocalDate toDate
) {
}
