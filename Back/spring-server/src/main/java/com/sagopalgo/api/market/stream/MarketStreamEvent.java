package com.sagopalgo.api.market.stream;

import java.time.Instant;
import java.util.List;

/** KRX 공개 시세만 허용합니다. 계좌 체결 통보·주문 판단 계약이 아닙니다. */
public record MarketStreamEvent(String eventId, String stockCode, String type, Instant marketTime,
    Instant receivedAt, String price, String volume, String cumulativeVolume,
    List<Level> asks, List<Level> bids, String session, String dateBasis) {
    public record Level(String price, String quantity) {}
}
