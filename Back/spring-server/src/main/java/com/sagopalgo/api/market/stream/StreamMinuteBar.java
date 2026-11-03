package com.sagopalgo.api.market.stream;

import java.math.BigDecimal;
import java.math.BigInteger;
import java.time.Instant;

/** 관측한 체결의 분봉. 누락 복구를 증명하지 않으므로 항상 OBSERVED_ONLY입니다. */
public record StreamMinuteBar(Instant minute, String open, String high, String low, String close,
    String volume, long trades, String firstOrder, String lastOrder, String coverage) {
    public static StreamMinuteBar first(MarketStreamEvent e) {
        String key=order(e);
        return new StreamMinuteBar(e.marketTime().truncatedTo(java.time.temporal.ChronoUnit.MINUTES),
            e.price(),e.price(),e.price(),e.price(),e.volume(),1,key,key,"OBSERVED_ONLY");
    }
    public StreamMinuteBar add(MarketStreamEvent e) {
        String key=order(e);
        return new StreamMinuteBar(minute,key.compareTo(firstOrder)<0?e.price():open,
            new BigDecimal(high).max(new BigDecimal(e.price())).toPlainString(),
            new BigDecimal(low).min(new BigDecimal(e.price())).toPlainString(),
            key.compareTo(lastOrder)>0?e.price():close,new BigInteger(volume).add(new BigInteger(e.volume())).toString(),
            trades+1,key.compareTo(firstOrder)<0?key:firstOrder,key.compareTo(lastOrder)>0?key:lastOrder,"OBSERVED_ONLY");
    }
    public static String order(MarketStreamEvent e) {
        return e.marketTime()+"|"+String.format("%030d",new BigInteger(e.cumulativeVolume()));
    }
}
