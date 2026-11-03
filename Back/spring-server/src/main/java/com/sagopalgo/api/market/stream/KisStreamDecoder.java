package com.sagopalgo.api.market.stream;

import java.math.BigDecimal;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.time.format.ResolverStyle;
import java.util.*;

/** 2026-11-03 공식 H0STCNT0(47), H0STASP0(63) 컬럼 계약. 암호화 계좌 통보는 받지 않습니다. */
public final class KisStreamDecoder {
    private static final ZoneId KOREA=ZoneId.of("Asia/Seoul");
    private static final DateTimeFormatter DATE=DateTimeFormatter.ofPattern("uuuuMMdd").withResolverStyle(ResolverStyle.STRICT);
    private static final DateTimeFormatter TIME=DateTimeFormatter.ofPattern("HHmmss").withResolverStyle(ResolverStyle.STRICT);
    public List<MarketStreamEvent> decode(String frame, Instant received) {
        if(frame==null || frame.length()>262144) throw invalid();
        String[] envelope=frame.split("\\|",4);
        if(envelope.length!=4 || !"0".equals(envelope[0])) throw invalid();
        boolean trade="H0STCNT0".equals(envelope[1]);
        if(!trade && !"H0STASP0".equals(envelope[1])) throw invalid();
        int width=trade ? 47 : 63;
        if(!envelope[2].matches("[0-9]{1,3}")) throw invalid();
        int count=Integer.parseInt(envelope[2]);
        String[] values=envelope[3].split("\\^",-1);
        if(count<1 || count>100 || values.length!=count*width) throw invalid();
        List<MarketStreamEvent> result=new ArrayList<>();
        for(int n=0;n<count;n++) {
            String[] f=Arrays.copyOfRange(values,n*width,(n+1)*width);
            if(!f[0].matches("[0-9]{6}")) throw invalid();
            if(!(trade?f[43]:f[2]).matches("[A-Za-z0-9]{0,4}")) throw invalid();
            LocalDate date=trade ? LocalDate.parse(f[33],DATE) : received.atZone(KOREA).toLocalDate();
            Instant at=LocalDateTime.of(date,LocalTime.parse(f[1],TIME)).atZone(KOREA).toInstant();
            if(at.isAfter(received.plusSeconds(5)) || at.isBefore(received.minusSeconds(86400))) throw invalid();
            String price=null, volume=null, cumulative=null;
            List<MarketStreamEvent.Level> asks=new ArrayList<>(),bids=new ArrayList<>();
            if(trade) {
                price=number(f[2]);volume=integer(f[12]);cumulative=integer(f[13]);
                if(new BigDecimal(price).signum()<=0 || new BigDecimal(cumulative).compareTo(new BigDecimal(volume))<0) throw invalid();
            } else {
                for(int i=0;i<10;i++) {
                    asks.add(new MarketStreamEvent.Level(number(f[3+i]),integer(f[23+i])));
                    bids.add(new MarketStreamEvent.Level(number(f[13+i]),integer(f[33+i])));
                }
            }
            // 누적 거래량이 같은 충돌 체결은 저장 단계에서 감지하며 거래량에 중복 가산하지 않습니다.
            String identity=trade ? "TRADE|"+f[0]+"|"+date+"|"+cumulative
                : "QUOTE|"+date+"|"+String.join("^",f);
            result.add(new MarketStreamEvent(hash(identity),f[0],trade?"TRADE":"QUOTE",at,received,
                price,volume,cumulative,List.copyOf(asks),List.copyOf(bids),trade?f[43]:f[2],
                trade?"PROVIDER_DATE":"RECEIVE_DATE_INFERRED"));
        }
        return List.copyOf(result);
    }
    private String integer(String text) { if(!text.matches("[0-9]{1,24}")) throw invalid();return new java.math.BigInteger(text).toString(); }
    private String number(String text) { if(!text.matches("[0-9]{1,24}(\\.[0-9]{1,6})?")) throw invalid();return new BigDecimal(text).toPlainString(); }
    public static String hash(String text) {
        return com.sagopalgo.api.common.util.ContentHash.sha256(text);
    }
    private IllegalArgumentException invalid() {return new IllegalArgumentException("INVALID_KIS_PUBLIC_STREAM");}
}
