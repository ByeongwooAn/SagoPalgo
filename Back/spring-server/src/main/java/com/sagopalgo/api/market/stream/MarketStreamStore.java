package com.sagopalgo.api.market.stream;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MarketStreamStore {
    private final MarketStreamMapper mapper;
    private final ObjectMapper json;
    public MarketStreamStore(MarketStreamMapper mapper,ObjectMapper json) {this.mapper=mapper;this.json=json;}
    public void verify() {mapper.verify();}
    @Transactional
    public boolean append(MarketStreamEvent event) {
        String encoded=write(event);
        if(mapper.insert(event.eventId(),event.stockCode(),event.type(),utc(event.marketTime()),utc(event.receivedAt()),encoded)==0) {
            MarketStreamEvent old=read(mapper.event(event.eventId()),MarketStreamEvent.class);
            // 수신 시각만 다른 재수신은 중복입니다. 같은 거래 식별자의 가격/수량 충돌은 차단합니다.
            if(!old.stockCode().equals(event.stockCode()) || !old.type().equals(event.type()) ||
                !old.marketTime().equals(event.marketTime()) || !Objects.equals(old.price(),event.price()) ||
                !Objects.equals(old.volume(),event.volume()) || !Objects.equals(old.cumulativeVolume(),event.cumulativeVolume()))
                throw new IllegalStateException("STREAM_EVENT_CONFLICT");
            return false;
        }
        if("TRADE".equals(event.type())) {
            StreamMinuteBar first=StreamMinuteBar.first(event);
            LocalDateTime minute=utc(first.minute());
            int created=mapper.seed(event.stockCode(),minute,write(first));
            // INSERT와 행 잠금/집계는 같은 트랜잭션이므로 중복/실패 시 거래량도 롤백됩니다.
            String locked=mapper.lock(event.stockCode(),minute);
            if(created==0) mapper.update(event.stockCode(),minute,write(read(locked,StreamMinuteBar.class).add(event)));
        }
        return true;
    }
    @Transactional(readOnly=true)
    public List<StreamMinuteBar> minutes(String stock,Instant from) {
        var bars=new ArrayList<>(mapper.minutes(stock,utc(from)).stream().map(s -> read(s,StreamMinuteBar.class)).toList());
        Collections.reverse(bars);return List.copyOf(bars);
    }
    private LocalDateTime utc(Instant at) {return LocalDateTime.ofInstant(at,ZoneOffset.UTC);}
    private String write(Object o) {try{return json.writeValueAsString(o);}catch(Exception e){throw new IllegalStateException("STREAM_STORAGE_UNAVAILABLE");}}
    private <T>T read(String s,Class<T> type) {try{return json.readValue(s,type);}catch(Exception e){throw new IllegalStateException("STREAM_STORAGE_UNAVAILABLE");}}
}
