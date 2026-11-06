package com.sagopalgo.api.market.stream;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.*;
import com.sagopalgo.api.common.util.ContentHash;
import jakarta.annotation.PreDestroy;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.channels.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.Consumer;
import org.springframework.beans.factory.annotation.*;
import org.springframework.stereotype.Component;

/** Append-only metadata, independent of the market DB. Async acceptance is not durability. */
@Component
public class StreamOperationsJournal implements AutoCloseable {
    static final String VERSION="SAGOPALGO_STREAM_OPERATIONS_V1",ZERO="0".repeat(64);
    static final int MAX_FILES=1024,MAX_LINE=8192;
    static final long READ_FILE_LIMIT=64L*1024*1024,READ_DIRECTORY_LIMIT=1024L*1024*1024;
    static final ObjectMapper JSON=new ObjectMapper().enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
        .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    enum Kind {START,LIFECYCLE,COUNTERS,END}
    record Counters(long receivedPublicFrames,long decodedEvents,long storageInsertions,long nonInsertions,
                    long storageFailures,long retiredCompletions,long inFlightStorage) {
        Counters {
            if(receivedPublicFrames<0 || decodedEvents<0 || storageInsertions<0 || nonInsertions<0 || storageFailures<0 || retiredCompletions<0 || inFlightStorage<0)
                throw new IllegalArgumentException("JOURNAL_COUNTER_INVALID");
        }
        static Counters zero() {return new Counters(0,0,0,0,0,0,0);}
        boolean follows(Counters old) {return receivedPublicFrames>=old.receivedPublicFrames && decodedEvents>=old.decodedEvents &&
            storageInsertions>=old.storageInsertions && nonInsertions>=old.nonInsertions && storageFailures>=old.storageFailures && retiredCompletions>=old.retiredCompletions;}
    }
    record Operation(long sourceSequence,long generation,String state,String code,String observedAt,long elapsedNanos,Counters counters) {
        Operation {
            if(sourceSequence<0 || generation<0 || elapsedNanos<0 || counters==null)throw new IllegalArgumentException("JOURNAL_OPERATION_INVALID");
            Instant.parse(observedAt);
            if(!STATES.contains(state) || code!=null && !CODES.contains(code))throw new IllegalArgumentException("JOURNAL_OPERATION_INVALID");
        }
    }
    record Body(String schemaVersion,UUID sessionId,UUID clockDomain,boolean utcSynchronized,long index,Kind kind,Operation operation,String previousHash) {}
    record Entry(Body entry,String hash) {}
    record Status(boolean enabled,String state,UUID sessionId,long lastDurableIndex,int queued,String failureCode) {}
    record Settings(boolean enabled,Path directory,int capacity,long maxSessionBytes,long maxDirectoryBytes,
                    Duration startTimeout,Duration writeTimeout,Duration closeTimeout) {
        Settings {
            if(directory==null || capacity<2 || capacity>1024 || maxSessionBytes<1024 || maxSessionBytes>READ_FILE_LIMIT ||
                maxDirectoryBytes<maxSessionBytes || maxDirectoryBytes>READ_DIRECTORY_LIMIT)throw new IllegalArgumentException("JOURNAL_SETTINGS_INVALID");
            for(var d:List.of(startTimeout,writeTimeout,closeTimeout))
                if(d.isNegative() || d.toMillis()<1 || d.compareTo(Duration.ofSeconds(10))>0)throw new IllegalArgumentException("JOURNAL_SETTINGS_INVALID");
        }
    }
    interface Sink extends AutoCloseable {void appendForced(byte[] bytes) throws IOException;void close() throws IOException;}
    interface SinkFactory {Sink create(Path file) throws IOException;}
    static final class FileSink implements Sink {
        private final FileChannel channel;
        FileSink(Path path) throws IOException {channel=FileChannel.open(path,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS);}
        public void appendForced(byte[] bytes) throws IOException {
            ByteBuffer buffer=ByteBuffer.wrap(bytes);while(buffer.hasRemaining())channel.write(buffer);channel.force(true);
        }
        public void close() throws IOException {channel.close();}
    }
    private record Pending(Kind kind,Operation operation) {}
    private static final Set<String> STATES=Set.of("SESSION_START","SESSION_END","COUNTERS","CONNECTING","SUBSCRIBING","CONNECTED",
        "RECONNECTING","FAILED","STABLE","DATA_READY","DISABLED");
    private static final Set<String> CODES=Set.of("STORAGE_025_REQUIRED","CONFIGURATION_REQUIRED","CONNECTION_FAILED","CONNECT_TIMEOUT",
        "SUBSCRIBE_TIMEOUT","HEARTBEAT_TIMEOUT","RETRY_BUDGET_RESET","SUBSCRIBE_FAILED","FRAME_LIMIT","PONG_FAILED",
        "SUBSCRIPTION_REJECTED","INVALID_FRAME","STORAGE_OR_PROTOCOL_FAILURE","CONNECTION_CLOSED","UNSUPPORTED_BINARY_FRAME",
        "COLLECTOR_STOPPED","OPERATIONS_JOURNAL_REQUIRED","OPERATIONS_JOURNAL_FAILED");
    private final Settings settings;
    private final SinkFactory sinkFactory;
    private final ArrayBlockingQueue<Pending> queue;
    private final ExecutorService writer=Executors.newSingleThreadExecutor(r->{var t=new Thread(r,"stream-operations-journal");t.setDaemon(true);return t;});
    private final CountDownLatch initialized=new CountDownLatch(1),finished=new CountDownLatch(1);
    private final AtomicReference<String> failure=new AtomicReference<>();
    private volatile boolean started,ready,closing,closed,everReady;
    private volatile long lastDurable,writingSince;
    private volatile UUID sessionId;
    private UUID clockDomain;
    private Operation initial;
    private volatile Operation lastOperation;
    private Consumer<String> failureListener=code->{};

    @Autowired public StreamOperationsJournal(@Value("${sagopalgo.market.stream.journal-enabled:false}") boolean enabled,
        @Value("${sagopalgo.market.stream.journal-directory:data/stream-operations}") String directory,
        @Value("${sagopalgo.market.stream.journal-capacity:256}") int capacity,
        @Value("${sagopalgo.market.stream.journal-max-session-bytes:16777216}") long sessionBytes,
        @Value("${sagopalgo.market.stream.journal-max-directory-bytes:268435456}") long directoryBytes) {
        this(new Settings(enabled,Path.of(directory),capacity,sessionBytes,directoryBytes,Duration.ofSeconds(2),Duration.ofSeconds(2),Duration.ofMillis(500)),FileSink::new);
    }
    StreamOperationsJournal(Settings settings,SinkFactory factory) {this.settings=settings;this.sinkFactory=factory;queue=new ArrayBlockingQueue<>(settings.capacity());}
    static StreamOperationsJournal disabled() {return new StreamOperationsJournal(false,"data/stream-operations",256,16777216,268435456);}
    void start(UUID domain,Operation start,Consumer<String> onFailure) {
        synchronized(this) {
        if(!settings.enabled())return;
        if(started || closing)throw new IllegalStateException("JOURNAL_ALREADY_STARTED");
        if(!start.state().equals("SESSION_START") || start.sourceSequence()!=0)throw new IllegalArgumentException("JOURNAL_START_INVALID");
        started=true;sessionId=UUID.randomUUID();clockDomain=Objects.requireNonNull(domain);initial=lastOperation=start;failureListener=onFailure;
        writer.execute(this::writeLoop);
        }
        try {if(!initialized.await(settings.startTimeout().toMillis(),TimeUnit.MILLISECONDS))fail("JOURNAL_START_TIMEOUT");}
        catch(InterruptedException e) {Thread.currentThread().interrupt();fail("JOURNAL_START_INTERRUPTED");}
        if(!ready || failure.get()!=null)throw new IllegalStateException("JOURNAL_START_FAILED");
    }
    boolean enabled() {return settings.enabled();}
    boolean healthy() {
        long start=writingSince;
        if(start!=0 && System.nanoTime()-start>settings.writeTimeout().toNanos())fail("JOURNAL_WRITE_TIMEOUT");
        return !settings.enabled() || ready && failure.get()==null;
    }
    Status status() {return new Status(settings.enabled(),!settings.enabled()?"DISABLED":failure.get()!=null?"FAILED":closed?"CLOSED":closing?"CLOSING":ready?"READY":"NOT_READY",sessionId,lastDurable,queue.size(),failure.get());}
    synchronized boolean append(Kind kind,Operation operation) {
        if(!settings.enabled())return true;
        if(!ready || closing || failure.get()!=null)return false;
        if(kind!=Kind.LIFECYCLE && kind!=Kind.COUNTERS)throw new IllegalArgumentException("JOURNAL_KIND_INVALID");
        if(!queue.offer(new Pending(kind,operation))) {fail("JOURNAL_QUEUE_FULL");return false;}
        lastOperation=operation;return true;
    }
    private void fail(String code) {
        if(failure.compareAndSet(null,code) && everReady)failureListener.accept(code);
    }
    private void writeLoop() {
        try {
            Path directory=settings.directory().toAbsolutePath().normalize();
            Files.createDirectories(directory);if(Files.isSymbolicLink(directory))throw new IOException();
            try(var lockChannel=FileChannel.open(directory.resolve(".writer.lock"),StandardOpenOption.CREATE,StandardOpenOption.WRITE,LinkOption.NOFOLLOW_LINKS)) {
                FileLock lock;
                try {lock=lockChannel.tryLock();} catch(OverlappingFileLockException e) {throw new IllegalStateException("JOURNAL_IN_USE");}
                if(lock==null)throw new IllegalStateException("JOURNAL_IN_USE");
                try(lock) {
                    long existing=0;int count=0;
                    try(var files=Files.newDirectoryStream(directory,"session-*.jsonl")) {
                        for(Path path:files) {
                            if(++count>=MAX_FILES || Files.isSymbolicLink(path) || !Files.isRegularFile(path,LinkOption.NOFOLLOW_LINKS))throw new IllegalStateException("JOURNAL_DIRECTORY_LIMIT");
                            existing=Math.addExact(existing,Files.size(path));
                            if(existing>=settings.maxDirectoryBytes())throw new IllegalStateException("JOURNAL_DIRECTORY_LIMIT");
                        }
                    }
                    if(failure.get()!=null)return;
                    try(Sink sink=sinkFactory.create(directory.resolve("session-"+sessionId+".jsonl"))) {
                        long bytes=0,index=0;String previous=ZERO;
                        Pending pending=new Pending(Kind.START,initial);
                        while(failure.get()==null) {
                            var body=new Body(VERSION,sessionId,clockDomain,false,++index,pending.kind(),pending.operation(),previous);
                            String hash=ContentHash.sha256(JSON.writeValueAsString(body));
                            byte[] encoded=(JSON.writeValueAsString(new Entry(body,hash))+"\n").getBytes(java.nio.charset.StandardCharsets.UTF_8);
                            if(encoded.length>MAX_LINE || bytes+encoded.length>settings.maxSessionBytes() || existing+bytes+encoded.length>settings.maxDirectoryBytes())
                                throw new IllegalStateException("JOURNAL_SIZE_LIMIT");
                            writingSince=System.nanoTime();sink.appendForced(encoded);writingSince=0;
                            bytes+=encoded.length;previous=hash;lastDurable=index;
                            if(pending.kind()==Kind.START) {ready=true;everReady=true;initialized.countDown();}
                            if(pending.kind()==Kind.END || failure.get()!=null)break;
                            pending=queue.take();
                        }
                    }
                }
            }
        } catch(InterruptedException e) {Thread.currentThread().interrupt();fail("JOURNAL_WRITER_INTERRUPTED");}
        catch(Exception e) {
            String code=e instanceof IllegalStateException && Set.of("JOURNAL_IN_USE","JOURNAL_DIRECTORY_LIMIT","JOURNAL_SIZE_LIMIT").contains(e.getMessage())?e.getMessage():"JOURNAL_IO_FAILED";
            fail(code);
        } finally {writingSince=0;ready=false;closed=true;initialized.countDown();finished.countDown();writer.shutdown();}
    }
    boolean finish(Operation end) {
        synchronized(this) {
            if(!settings.enabled())return true;
            if(!closing) {
                closing=true;
                if(!started) {closed=true;finished.countDown();writer.shutdown();}
                else if(failure.get()==null && !queue.offer(new Pending(Kind.END,end)))fail("JOURNAL_QUEUE_FULL");
            }
        }
        try {
            if(!finished.await(settings.closeTimeout().toMillis(),TimeUnit.MILLISECONDS)) {fail("JOURNAL_CLOSE_TIMEOUT");writer.shutdownNow();return false;}
        } catch(InterruptedException e) {Thread.currentThread().interrupt();fail("JOURNAL_CLOSE_INTERRUPTED");return false;}
        return failure.get()==null;
    }
    @Override @PreDestroy public void close() {
        Operation last=lastOperation;
        finish(last==null?null:new Operation(last.sourceSequence(),last.generation(),"SESSION_END",null,last.observedAt(),last.elapsedNanos(),last.counters()));
    }
}
