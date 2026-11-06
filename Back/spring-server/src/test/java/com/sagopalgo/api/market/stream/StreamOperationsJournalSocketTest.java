package com.sagopalgo.api.market.stream;

import static org.assertj.core.api.Assertions.*;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import java.io.IOException;
import java.nio.file.*;
import java.time.*;
import java.util.*;
import java.util.concurrent.atomic.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.ExpectedCount;

class StreamOperationsJournalSocketTest {
    @TempDir Path root;
    KisStreamSocketRecoveryTest.Fixture fixture(StreamOperationsJournal journal) throws Exception {
        return new KisStreamSocketRecoveryTest.Fixture(KisStreamSocketRecoveryTest.timing(),null,new LoopbackWebSocketServer(),
            Clock.fixed(KisStreamSocketRecoveryTest.NOW,ZoneOffset.UTC),journal);
    }
    @Test void twoCollectorInstancesKeepOldRunAndCountersWithoutReplayingItsLiveState() throws Exception {
        UUID oldId;byte[] original;
        var first=new StreamOperationsJournal(StreamOperationsJournalTest.settings(root),StreamOperationsJournal.FileSink::new);
        try(var f=fixture(first)) {
            f.start();var peer=f.server.next();f.subscriptions(peer,true);
            peer.text(KisStreamSocketRecoveryTest.trade("1"));peer.text(MarketStreamTest.quote());peer.text(KisStreamSocketRecoveryTest.trade("1"));
            KisStreamSocketRecoveryTest.until(()->f.connection.recoverySnapshot().counters().nonInsertions()==1);
            f.connection.stop();oldId=first.status().sessionId();
            assertThat(first.status().state()).isEqualTo("CLOSED");
            original=Files.readAllBytes(StreamOperationsJournalTest.session(root,oldId));
        }
        var second=new StreamOperationsJournal(StreamOperationsJournalTest.settings(root),StreamOperationsJournal.FileSink::new);
        try(var f=fixture(second)) {
            f.start();var peer=f.server.next();f.subscriptions(peer,true);
            KisStreamSocketRecoveryTest.until(()->f.state().equals("CONNECTED"));
            assertThat(f.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).state()).isEqualTo("WAITING_DATA");
            assertThat(f.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).trade()).isNull();
            assertThat(second.status().sessionId()).isNotEqualTo(oldId);
        }
        var sessions=StreamOperationsJournalTest.sessions(root);
        assertThat(sessions).hasSize(2).allMatch(s->s.get("status").equals("CLEAN_END"));
        var old=sessions.stream().filter(s->s.get("sessionId").equals(oldId)).findFirst().orElseThrow();
        var last=(StreamOperationsJournal.Operation)old.get("lastOperation");
        assertThat(last.counters().receivedPublicFrames()).isEqualTo(3);
        assertThat(last.counters().decodedEvents()).isEqualTo(3);
        assertThat(last.counters().storageInsertions()).isEqualTo(2);
        assertThat(last.counters().nonInsertions()).isEqualTo(1);
        assertThat(Files.readAllBytes(StreamOperationsJournalTest.session(root,oldId))).isEqualTo(original);
    }
    @Test void unavailableJournalPreventsApprovalAndProviderConnection() throws Exception {
        var journal=new StreamOperationsJournal(StreamOperationsJournalTest.settings(root),path->{throw new IOException("secret-path");});
        try(var f=fixture(journal)) {
            f.approval.reset();f.approval.expect(ExpectedCount.never(),requestTo("https://openapi.koreainvestment.com:9443/oauth2/Approval"))
                .andRespond(withSuccess("{}",MediaType.APPLICATION_JSON));
            f.start();assertThat(f.state()).isEqualTo("FAILED");
            assertThat(f.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).diagnostic()).isEqualTo("OPERATIONS_JOURNAL_REQUIRED");
            assertThat(f.server.accepted()).isZero();assertThat(f.connection.recoverySnapshot().attempts()).isZero();
        }
    }
    @Test void asynchronousRecordFailureTerminatesCollectorWithoutRetryingUnrecordedConnections() throws Exception {
        var writes=new AtomicInteger();
        var journal=new StreamOperationsJournal(StreamOperationsJournalTest.settings(root),path->{
            var sink=new StreamOperationsJournal.FileSink(path);
            return new StreamOperationsJournal.Sink() {
                public void appendForced(byte[] bytes) throws IOException {if(writes.incrementAndGet()>1)throw new IOException("secret-disk-error");sink.appendForced(bytes);}
                public void close() throws IOException {sink.close();}
            };
        });
        try(var f=fixture(journal)) {
            f.approval.reset();f.approval.expect(ExpectedCount.max(1),requestTo("https://openapi.koreainvestment.com:9443/oauth2/Approval"))
                .andRespond(withSuccess("{\"approval_key\":\"synthetic-approval\"}",MediaType.APPLICATION_JSON));
            f.start();KisStreamSocketRecoveryTest.until(()->f.state().equals("FAILED"));
            assertThat(f.connection.recoverySnapshot().terminal()).isTrue();
            assertThat(f.hub.snapshot("005930",KisStreamSocketRecoveryTest.NOW).diagnostic()).isEqualTo("OPERATIONS_JOURNAL_FAILED");
            Thread.sleep(150);
            assertThat(f.connection.recoverySnapshot().attempts()).isEqualTo(1);
            assertThat(f.server.accepted()).isLessThanOrEqualTo(1);
        }
        assertThat(journal.status().failureCode()).isEqualTo("JOURNAL_IO_FAILED");
    }
}
