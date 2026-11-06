package com.sagopalgo.api.market.stream;

import com.sagopalgo.api.config.MarketStreamProperties;
import java.time.*;
import java.util.*;
import org.springframework.stereotype.Service;

@Service
public class MarketStreamHub {
    public record Snapshot(String contractVersion,boolean enabled,int staleSeconds,String provider,String exchange,String currency,
        String stockCode,String connectionState,String state,String diagnostic,Instant checkedAt,
        MarketStreamEvent trade,MarketStreamEvent quote,List<StreamMinuteBar> minutes,
        boolean gapDetected,boolean usableForTrading,String investorFlowStatus) {}
    private record Cached(Instant at,List<StreamMinuteBar> bars) {}
    private final MarketStreamProperties policy;
    private final MarketStreamStore store;
    private final MarketAvailabilityJournal availability;
    private final Map<String,MarketStreamEvent> trades=new HashMap<>(),quotes=new HashMap<>();
    private final Map<String,Cached> cached=new HashMap<>();
    private String connection="DISABLED",diagnostic=null;
    private long generation;
    MarketStreamHub(MarketStreamProperties policy,MarketStreamStore store) {this(policy,store,null);}
    @org.springframework.beans.factory.annotation.Autowired
    public MarketStreamHub(MarketStreamProperties policy,MarketStreamStore store,MarketAvailabilityJournal availability) {
        this.policy=policy;this.store=store;this.availability=availability;
    }
    public void verifyStorage() {store.verify();if(availability!=null)availability.verify();}
    public synchronized void connection(String state,String code) {
        connection=state;diagnostic=code;
        if(!"CONNECTED".equals(state)) {generation++;trades.clear();quotes.clear();}
    }
    public void accept(MarketStreamEvent event) {
        if(!policy.enabled() || !policy.stockCodes().contains(event.stockCode())) throw new IllegalArgumentException("UNSUBSCRIBED_SYMBOL");
        final long epoch;
        synchronized(this) {epoch=generation;}
        store.appendCommitted(event,()->{
            try {
                if(availability==null) publish(event,epoch);
                else availability.publish(event,()->publish(event,epoch));
            } catch(RuntimeException error) {
                connection("FAILED","AVAILABILITY_RECORD_FAILED");
                throw new IllegalStateException("AVAILABILITY_RECORD_FAILED");
            }
        });
    }
    private synchronized boolean publish(MarketStreamEvent event,long epoch) {
        if(epoch!=generation) return false;
        var target="TRADE".equals(event.type()) ? trades : quotes;
        var old=target.get(event.stockCode());
        if(old==null || event.marketTime().isAfter(old.marketTime()) ||
            (event.marketTime().equals(old.marketTime()) && (("TRADE".equals(event.type()) &&
                new java.math.BigInteger(event.cumulativeVolume()).compareTo(new java.math.BigInteger(old.cumulativeVolume()))>0) ||
                ("QUOTE".equals(event.type()) && event.receivedAt().isAfter(old.receivedAt())))))
            {target.put(event.stockCode(),event);return true;}
        return false;
    }
    public synchronized Snapshot snapshot(String stock,Instant now) {
        if(stock==null || !stock.matches("[0-9]{6}")) throw new IllegalArgumentException("INVALID_STOCK_CODE");
        var trade=trades.get(stock);var quote=quotes.get(stock);
        String state=!policy.enabled()?"DISABLED":!policy.stockCodes().contains(stock)?"NOT_SUBSCRIBED":
            !"CONNECTED".equals(connection)?connection:trade==null || quote==null?"WAITING_DATA":
            fresh(trade,now)&&fresh(quote,now)?"LIVE":"STALE";
        List<StreamMinuteBar> bars=List.of();
        if(policy.enabled() && policy.stockCodes().contains(stock)) {
            Cached value=cached.get(stock);
            if(value==null || !now.isBefore(value.at().plusSeconds(1))) {
                value=new Cached(now,store.minutes(stock,now.minusSeconds(7200)));cached.put(stock,value);
            }
            bars=value.bars();
        }
        return new Snapshot("KIS_KRX_STREAM_V1",policy.enabled(),policy.staleSeconds(),"KIS","KRX","KRW",stock,connection,state,
            diagnostic,now,trade,quote,bars,true,false,"NOT_SUBSCRIBED");
    }
    private boolean fresh(MarketStreamEvent e,Instant now) {
        return !e.receivedAt().isBefore(now.minusSeconds(policy.staleSeconds())) &&
            !e.marketTime().isBefore(now.minusSeconds(policy.staleSeconds())) && !e.marketTime().isAfter(now.plusSeconds(5));
    }
}
