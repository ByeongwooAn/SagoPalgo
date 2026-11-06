package com.sagopalgo.api.market.stream;

import com.sagopalgo.api.common.util.ContentHash;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.*;
import java.util.function.BooleanSupplier;
import org.springframework.beans.factory.annotation.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** Immutable upper-bound observations after source commit and input publication. */
@Service
public class MarketAvailabilityJournal {
    private final boolean enabled;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final MarketAvailabilityClock clock;
    private final TransactionTemplate committed;
    @Autowired public MarketAvailabilityJournal(JdbcTemplate jdbc,ObjectMapper json,MarketAvailabilityClock clock,
        PlatformTransactionManager manager,@Value("${sagopalgo.market.stream.availability-enabled:false}") boolean enabled) {
        this.enabled=enabled;this.jdbc=jdbc;this.json=json;this.clock=clock;
        this.committed=new TransactionTemplate(manager);
        this.committed.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
        this.committed.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
        this.committed.setTimeout(10);
    }
    public void verify() {
        if(enabled) jdbc.queryForObject("SELECT COUNT(*) FROM market_stream_availability WHERE 1=0",Integer.class);
    }
    public void publish(MarketStreamEvent event,BooleanSupplier publication) {
        var sourceCommitted=clock.mark();
        // afterCommit callbacks retain the old JDBC resources; a new transaction
        // both confirms committed visibility and durably writes the observation.
        committed.executeWithoutResult(status->{
            var payloads=jdbc.queryForList("SELECT payload FROM market_stream_events WHERE event_id=?",String.class,event.eventId());
            if(payloads.isEmpty())return; // nested/savepoint rollback never publishes
            if(payloads.size()!=1)throw new IllegalStateException("AVAILABILITY_SOURCE_MISMATCH");
            String payload=payloads.get(0);
            try {
                MarketStreamEvent stored=json.readValue(payload,MarketStreamEvent.class);
                if(!stored.equals(event)) throw new IllegalStateException();
            } catch(Exception e) {throw new IllegalStateException("AVAILABILITY_SOURCE_MISMATCH");}
            if(!enabled) {publication.getAsBoolean();return;}
            if(!publication.getAsBoolean()) return; // stale generation/older event was not projected
            var exposed=clock.mark(); // after the cache monitor has been released
            String quality=sourceCommitted.stable()&&exposed.stable()?"MONOTONIC_STABLE":"CLOCK_STEP_DETECTED";
            jdbc.update("INSERT INTO market_stream_availability(event_id,content_hash,clock_domain,commit_observed_at,input_published_at,commit_elapsed_ns,published_elapsed_ns,clock_quality) VALUES(?,?,?,?,?,?,?,?)",
                event.eventId(),ContentHash.sha256(payload),clock.domain(),utc(sourceCommitted.at()),utc(exposed.at()),
                sourceCommitted.elapsedNanos(),exposed.elapsedNanos(),quality);
        });
    }
    private LocalDateTime utc(Instant at) {return LocalDateTime.ofInstant(at,ZoneOffset.UTC);}
}
