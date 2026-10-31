package com.sagopalgo.api.market.model;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.List;

/** KOSPI 조회 시각과 실제 거래일을 분리합니다. 일봉은 오래된 순서입니다. */
public record MarketIndexSnapshot(String status, String provider, String message,
    BigDecimal value, BigDecimal changeRate, Instant receivedAt, List<Point> points) {
    public record Point(LocalDate date, BigDecimal close) {}
}
