package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import java.io.*;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class StreamOperationsJournalTest {
    @TempDir Path root;
    static StreamOperationsJournal.Settings settings(Path directory) {
        return new StreamOperationsJournal.Settings(true,directory,8,16384,65536,Duration.ofSeconds(1),Duration.ofSeconds(1),Duration.ofMillis(250));
    }
    static StreamOperationsJournal.Operation op(long sequence,String state) {
        return new StreamOperationsJournal.Operation(sequence,sequence,state,null,"2026-11-06T01:00:00Z",sequence*1000,StreamOperationsJournal.Counters.zero());
    }
    static void start(StreamOperationsJournal journal) {journal.start(UUID.randomUUID(),op(0,"SESSION_START"),code->{});}
    static void durable(StreamOperationsJournal journal,long index) throws InterruptedException {
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(3);
        while(journal.status().lastDurableIndex()<index && System.nanoTime()<deadline)Thread.sleep(5);
        assertThat(journal.status().lastDurableIndex()).isGreaterThanOrEqualTo(index);
    }
    @SuppressWarnings("unchecked") static List<Map<String,Object>> sessions(Path path) throws IOException {
        return (List<Map<String,Object>>)StreamOperationsJournalInspector.inspect(path,null,0,100).get("sessions");
    }
    static Path session(Path root,UUID id) {return root.resolve("session-"+id+".jsonl");}
    @Test void disabledDoesNotCreateFilesOrStartWriter() {
        Path missing=root.resolve("missing");
        try(var journal=new StreamOperationsJournal(false,missing.toString(),8,16384,65536)) {
            start(journal);assertThat(journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"))).isTrue();
            assertThat(journal.healthy()).isTrue();assertThat(journal.status().state()).isEqualTo("DISABLED");
        }
        assertThat(missing).doesNotExist();
    }
    @Test void restartCreatesDistinctSessionAndPreservesPreviousBytesAndClockDomain() throws Exception {
        UUID firstId;byte[] previous;
        try(var first=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {
            start(first);firstId=first.status().sessionId();first.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));
            assertThat(first.finish(op(1,"SESSION_END"))).isTrue();previous=Files.readAllBytes(session(root,firstId));
        }
        try(var second=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {
            start(second);assertThat(second.status().sessionId()).isNotEqualTo(firstId);
            second.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"SUBSCRIBING"));second.finish(op(1,"SESSION_END"));
        }
        assertThat(Files.readAllBytes(session(root,firstId))).isEqualTo(previous);
        assertThat(sessions(root)).hasSize(2).allMatch(s->s.get("status").equals("CLEAN_END"));
        assertThat(sessions(root).stream().map(s->s.get("clockDomain")).distinct().count()).isEqualTo(2);
    }
    @Test void duplicateWriterIsRejectedWithoutReplacingPriorSession() throws Exception {
        try(var first=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new);
            var second=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {
            start(first);byte[] before=Files.readAllBytes(session(root,first.status().sessionId()));
            assertThatThrownBy(()->start(second)).hasMessage("JOURNAL_START_FAILED");
            assertThat(second.status().failureCode()).isEqualTo("JOURNAL_IN_USE");
            assertThat(Files.readAllBytes(session(root,first.status().sessionId()))).isEqualTo(before);
        }
    }
    @Test void readerPagesWithoutRepairOrAssumingCrossSessionChronology() throws Exception {
        UUID id;
        try(var journal=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {
            start(journal);id=journal.status().sessionId();
            for(int i=1;i<=4;i++)journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(i,"CONNECTING"));
            journal.finish(op(4,"SESSION_END"));
        }
        byte[] original=Files.readAllBytes(session(root,id));
        var report=StreamOperationsJournalInspector.inspect(root,id,1,2);
        @SuppressWarnings("unchecked") var runs=(List<Map<String,Object>>)report.get("sessions");
        assertThat(runs.get(0).get("nextAfterIndex")).isEqualTo(3L);
        assertThat(report.get("crossSessionOrder")).isEqualTo("UNCONFIRMED");
        assertThat(report.get("writerActivity")).isEqualTo("NOT_DETERMINED");
        assertThat(Files.readAllBytes(session(root,id))).isEqualTo(original);
    }
    @ParameterizedTest @ValueSource(strings={"partial","hash","sequence","duplicate-key","null-kind","after-end"})
    void tamperingAndPartialTailRemainVisibleAndOriginalIsNotRepaired(String kind) throws Exception {
        UUID id;
        try(var journal=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {
            start(journal);id=journal.status().sessionId();journal.finish(op(0,"SESSION_END"));
        }
        Path file=session(root,id);String original=Files.readString(file);
        String changed=switch(kind) {
            case "partial"->original+"{\"entry\":";
            case "hash"->original.replaceFirst("\"hash\":\".","\"hash\":\"z");
            case "sequence"->original.replaceFirst("\"index\":1","\"index\":9");
            case "duplicate-key"->original.replaceFirst("\"utcSynchronized\":false","\"utcSynchronized\":false,\"utcSynchronized\":false");
            case "null-kind"->original.replaceFirst("\"kind\":\"START\"","\"kind\":null");
            default->original+original.lines().findFirst().orElseThrow()+"\n";
        };
        Files.writeString(file,changed);byte[] before=Files.readAllBytes(file);
        assertThat(sessions(root).get(0).get("status")).isEqualTo(kind.equals("partial")?"PARTIAL_TAIL":"CORRUPT");
        assertThat(Files.readAllBytes(file)).isEqualTo(before);
    }
    @Test void startupIoFailureIsSanitizedAndDoesNotCreateASuccessfulSession() {
        try(var journal=new StreamOperationsJournal(settings(root),path->{throw new IOException("private-file-path-secret");})) {
            assertThatThrownBy(()->start(journal)).hasMessage("JOURNAL_START_FAILED");
            assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_IO_FAILED");
            assertThat(journal.status().toString()).doesNotContain("private-file-path-secret");
        }
    }
    @Test void partialWriteFailureReportsPrefixAndNotCleanEnd() throws Exception {
        AtomicInteger writes=new AtomicInteger();AtomicReference<String> failure=new AtomicReference<>();
        try(var journal=new StreamOperationsJournal(settings(root),path->{
            var sink=new StreamOperationsJournal.FileSink(path);
            return new StreamOperationsJournal.Sink() {
                public void appendForced(byte[] bytes) throws IOException {
                    if(writes.incrementAndGet()==2) {sink.appendForced(Arrays.copyOf(bytes,bytes.length/2));throw new IOException("private-disk-error");}
                    sink.appendForced(bytes);
                }
                public void close() throws IOException {sink.close();}
            };
        })) {
            journal.start(UUID.randomUUID(),op(0,"SESSION_START"),failure::set);
            journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));
            long end=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            while(failure.get()==null && System.nanoTime()<end)Thread.sleep(5);
            assertThat(failure.get()).isEqualTo("JOURNAL_IO_FAILED");
            assertThat(journal.finish(op(1,"SESSION_END"))).isFalse();
        }
        assertThat(sessions(root).get(0).get("status")).isEqualTo("PARTIAL_TAIL");
        assertThat(sessions(root).get(0).get("verifiedEntries")).isEqualTo(1L);
    }
    @Test void blockedWriterHasBoundedShutdownAndDoesNotAcknowledgeCleanClose() throws Exception {
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var writes=new AtomicInteger();
        try(var journal=new StreamOperationsJournal(settings(root),path->{
            var sink=new StreamOperationsJournal.FileSink(path);
            return new StreamOperationsJournal.Sink() {
                public void appendForced(byte[] bytes) throws IOException {
                    if(writes.incrementAndGet()>1) {
                        entered.countDown();
                        try {release.await(3,TimeUnit.SECONDS);} catch(InterruptedException e) {Thread.currentThread().interrupt();throw new IOException();}
                    }
                    sink.appendForced(bytes);
                }
                public void close() throws IOException {sink.close();}
            };
        })) {
            start(journal);journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));
            assertThat(entered.await(1,TimeUnit.SECONDS)).isTrue();long at=System.nanoTime();
            assertThat(journal.finish(op(1,"SESSION_END"))).isFalse();
            assertThat(System.nanoTime()-at).isLessThan(TimeUnit.SECONDS.toNanos(1));
            assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_CLOSE_TIMEOUT");
        } finally {release.countDown();}
    }
    @Test void sizeLimitStopsWriterWithoutDeletingOrRewritingPrefix() throws Exception {
        var s=new StreamOperationsJournal.Settings(true,root,8,1024,4096,Duration.ofSeconds(1),Duration.ofSeconds(1),Duration.ofMillis(250));
        try(var journal=new StreamOperationsJournal(s,StreamOperationsJournal.FileSink::new)) {
            start(journal);Path file=session(root,journal.status().sessionId());byte[] initial=Files.readAllBytes(file);
            journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(2);
            while(journal.status().failureCode()==null && System.nanoTime()<deadline)Thread.sleep(5);
            assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_SIZE_LIMIT");
            assertThat(Files.readAllBytes(file)).startsWith(initial);
        }
    }
    @Test void arbitraryMessagesAndUnknownFieldsAreNotAcceptedAsOperations() {
        assertThatThrownBy(()->new StreamOperationsJournal.Operation(1,1,"FAILED","secret-from-provider","2026-11-06T01:00:00Z",1,StreamOperationsJournal.Counters.zero()))
            .hasMessage("JOURNAL_OPERATION_INVALID");
    }
    @Test void cliPreservesInputAndDoesNotOverwriteReportOrEchoBadPath() throws Exception {
        try(var journal=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {start(journal);journal.finish(op(0,"SESSION_END"));}
        Path output=root.resolve("inspection.json");String[] args={"--directory",root.toString(),"--output",output.toString()};
        assertThat(StreamOperationsJournalInspector.run(args)).isZero();byte[] saved=Files.readAllBytes(output);
        assertThat(StreamOperationsJournalInspector.run(args)).isEqualTo(2);assertThat(Files.readAllBytes(output)).isEqualTo(saved);
    }
    @Test void abruptChildJvmLeavesVerifiedUnfinishedPrefixAndNextRunDoesNotRewriteIt() throws Exception {
        var types=List.of(StreamOperationsJournalCrashFixture.class,StreamOperationsJournal.class,
            com.fasterxml.jackson.databind.ObjectMapper.class,com.fasterxml.jackson.core.JsonFactory.class,com.fasterxml.jackson.annotation.JsonCreator.class,
            org.springframework.stereotype.Component.class,org.springframework.beans.factory.annotation.Autowired.class,jakarta.annotation.PreDestroy.class);
        String classpath=types.stream().map(type->{try {return Path.of(type.getProtectionDomain().getCodeSource().getLocation().toURI()).toString();}
            catch(Exception e) {throw new IllegalStateException(e);}}).distinct().collect(java.util.stream.Collectors.joining(java.io.File.pathSeparator));
        Path childLog=root.resolve("child.log");
        var child=new ProcessBuilder(Path.of(System.getProperty("java.home"),"bin",System.getProperty("os.name").startsWith("Windows")?"java.exe":"java").toString(),
            "-cp",classpath,StreamOperationsJournalCrashFixture.class.getName(),root.toString()).redirectErrorStream(true).redirectOutput(childLog.toFile()).start();
        try {assertThat(child.waitFor(5,TimeUnit.SECONDS)).isTrue();assertThat(child.exitValue()).as(Files.readString(childLog)).isZero();}
        finally {if(child.isAlive())child.destroyForcibly();}
        var before=StreamOperationsJournalTest.sessions(root);assertThat(before).hasSize(1);
        assertThat(before.get(0).get("status")).isEqualTo("NO_END_MARKER");assertThat(before.get(0).get("verifiedEntries")).isEqualTo(2L);
        UUID old=(UUID)before.get(0).get("sessionId");byte[] prefix=Files.readAllBytes(session(root,old));
        try(var next=new StreamOperationsJournal(settings(root),StreamOperationsJournal.FileSink::new)) {start(next);next.finish(op(0,"SESSION_END"));}
        assertThat(Files.readAllBytes(session(root,old))).isEqualTo(prefix);
        assertThat(sessions(root)).hasSize(2).anyMatch(s->s.get("status").equals("CLEAN_END")).anyMatch(s->s.get("status").equals("NO_END_MARKER"));
    }
    @Test void queueOverflowIsReportedAndNeverBecomesCleanEnd() throws Exception {
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var writes=new AtomicInteger();
        var tiny=new StreamOperationsJournal.Settings(true,root,2,16384,65536,Duration.ofSeconds(1),Duration.ofSeconds(1),Duration.ofMillis(250));
        try(var journal=new StreamOperationsJournal(tiny,path->{
            var sink=new StreamOperationsJournal.FileSink(path);
            return new StreamOperationsJournal.Sink() {
                public void appendForced(byte[] bytes) throws IOException {
                    if(writes.incrementAndGet()==2) {entered.countDown();try {release.await(3,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException();}}
                    sink.appendForced(bytes);
                }
                public void close() throws IOException {sink.close();}
            };
        })) {
            start(journal);journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));assertThat(entered.await(1,TimeUnit.SECONDS)).isTrue();
            journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(2,"CONNECTING"));journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(3,"CONNECTING"));
            assertThat(journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(4,"CONNECTING"))).isFalse();
            assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_QUEUE_FULL");release.countDown();
            assertThat(journal.finish(op(4,"SESSION_END"))).isFalse();
        } finally {release.countDown();}
        assertThat(sessions(root)).noneMatch(s->s.get("status").equals("CLEAN_END"));
    }
    @Test void existingDirectoryBudgetIsEnforcedWithoutChangingOldFiles() throws Exception {
        Path old=root.resolve("session-"+UUID.randomUUID()+".jsonl");
        byte[] original=new byte[4096];Files.write(old,original);
        var limited=new StreamOperationsJournal.Settings(true,root,8,1024,4096,Duration.ofSeconds(1),Duration.ofSeconds(1),Duration.ofMillis(250));
        try(var journal=new StreamOperationsJournal(limited,StreamOperationsJournal.FileSink::new)) {
            assertThatThrownBy(()->start(journal)).hasMessage("JOURNAL_START_FAILED");
            assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_DIRECTORY_LIMIT");
        }
        assertThat(Files.readAllBytes(old)).isEqualTo(original);
        try(var files=Files.newDirectoryStream(root,"session-*.jsonl")) {assertThat(files).containsExactly(old);}
    }
    @Test void healthDetectsStalledWriteBeforeShutdown() throws Exception {
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var writes=new AtomicInteger();
        var shortWrite=new StreamOperationsJournal.Settings(true,root,8,16384,65536,Duration.ofSeconds(1),Duration.ofMillis(30),Duration.ofMillis(250));
        var notified=new AtomicReference<String>();
        try(var journal=new StreamOperationsJournal(shortWrite,path->{
            var sink=new StreamOperationsJournal.FileSink(path);
            return new StreamOperationsJournal.Sink() {
                public void appendForced(byte[] bytes) throws IOException {
                    if(writes.incrementAndGet()==2) {entered.countDown();try {release.await(3,TimeUnit.SECONDS);}catch(InterruptedException e){Thread.currentThread().interrupt();throw new IOException();}}
                    sink.appendForced(bytes);
                }
                public void close() throws IOException {sink.close();}
            };
        })) {
            journal.start(UUID.randomUUID(),op(0,"SESSION_START"),notified::set);
            journal.append(StreamOperationsJournal.Kind.LIFECYCLE,op(1,"CONNECTING"));
            assertThat(entered.await(1,TimeUnit.SECONDS)).isTrue();
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(1);
            while(journal.healthy() && System.nanoTime()<deadline)Thread.sleep(5);
            assertThat(journal.healthy()).isFalse();assertThat(notified.get()).isEqualTo("JOURNAL_WRITE_TIMEOUT");
            release.countDown();assertThat(journal.finish(op(1,"SESSION_END"))).isFalse();
        } finally {release.countDown();}
    }
}
