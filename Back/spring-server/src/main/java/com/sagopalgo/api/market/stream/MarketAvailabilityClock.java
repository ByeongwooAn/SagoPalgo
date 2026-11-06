package com.sagopalgo.api.market.stream;

import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.UUID;
import java.util.function.LongSupplier;
import org.springframework.stereotype.Component;

/** A causal process clock, explicitly not a certificate of external UTC accuracy. */
@Component
public class MarketAvailabilityClock {
    public record Mark(Instant at,long elapsedNanos,boolean stable) {}
    private final Clock wall;
    private final LongSupplier nanos;
    private final Instant anchor;
    private final long start;
    private final String domain=UUID.randomUUID().toString();
    private Instant last;
    private boolean unstable;
    public MarketAvailabilityClock() {this(Clock.systemUTC(),System::nanoTime);}
    MarketAvailabilityClock(Clock wall,LongSupplier nanos) {
        this.wall=wall;this.nanos=nanos;this.anchor=wall.instant();this.start=nanos.getAsLong();this.last=anchor.minusNanos(1000);
    }
    public String domain() {return domain;}
    public synchronized Mark mark() {
        long elapsed=nanos.getAsLong()-start;
        if(elapsed<0) throw new IllegalStateException("AVAILABILITY_MONOTONIC_CLOCK_INVALID");
        Instant projected=anchor.plusNanos(elapsed);
        if(Duration.between(projected,wall.instant()).abs().compareTo(Duration.ofMillis(250))>0) unstable=true;
        Instant at=ceil(projected);
        if(!at.isAfter(last)) at=last.plusNanos(1000);
        last=at;
        return new Mark(at,elapsed,!unstable);
    }
    static Instant ceil(Instant value) {
        Instant floor=value.truncatedTo(ChronoUnit.MICROS);
        return floor.equals(value)?floor:floor.plusNanos(1000);
    }
}
