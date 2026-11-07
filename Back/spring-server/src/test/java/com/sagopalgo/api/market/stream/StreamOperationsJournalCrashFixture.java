package com.sagopalgo.api.market.stream;

import java.nio.file.Path;
import java.time.*;
import java.util.UUID;

/** Owned child JVM only: deliberate halt after a forced prefix, without shutdown hooks. */
public final class StreamOperationsJournalCrashFixture {
    public static void main(String[] args) throws Exception {
        var journal=new StreamOperationsJournal(true,Path.of(args[0]).toString(),8,16384,65536);
        var zero=StreamOperationsJournal.Counters.zero();
        journal.start(UUID.randomUUID(),new StreamOperationsJournal.Operation(0,0,"SESSION_START",null,"2026-11-06T01:00:00Z",0,zero),code->{});
        journal.append(StreamOperationsJournal.Kind.LIFECYCLE,new StreamOperationsJournal.Operation(1,1,"CONNECTING",null,"2026-11-06T01:00:00Z",1000,zero));
        long until=System.nanoTime()+Duration.ofSeconds(3).toNanos();
        while(journal.status().lastDurableIndex()<2 && System.nanoTime()<until)Thread.sleep(5);
        if(journal.status().lastDurableIndex()!=2)throw new IllegalStateException("CHILD_PREFIX_NOT_DURABLE");
        Runtime.getRuntime().halt(0);
    }
}
