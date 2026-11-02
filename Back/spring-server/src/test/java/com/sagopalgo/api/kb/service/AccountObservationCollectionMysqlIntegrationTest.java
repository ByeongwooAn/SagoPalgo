package com.sagopalgo.api.kb.service;

import static com.sagopalgo.api.kb.service.AccountObservationFixtures.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import com.sagopalgo.api.config.AccountObservationCollectionProperties;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.controller.AccountObservationCollectionController;
import com.sagopalgo.api.kb.controller.AccountObservationHistoryController;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.mapper.AccountObservationCollectorMapper;
import com.sagopalgo.api.kb.mapper.AccountObservationMapper;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.nio.charset.StandardCharsets;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.*;
import java.util.concurrent.*;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.core.io.FileSystemResource;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/** 고정 루프백·DB 이름·마커를 확인한 전용 DB만 사용하며 모든 KB 호출은 mock입니다. */
@EnabledIfEnvironmentVariable(named="SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST",matches="true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AccountObservationCollectionMysqlIntegrationTest {
    private DriverManagerDataSource dataSource;
    private JdbcTemplate jdbc;
    private AccountObservationCollectorMapper mapper;
    private AccountObservationCollectorStore collector;
    private AccountObservationStore observations;
    private AccountObservationHistoryService history;
    private AccountObservationCollectionService service;
    private SecuritiesProviderProperties properties;
    private AccountObservationBinding binding;
    private AccountObservationCodec codec;
    private KbAccountSnapshotService observer;
    private final Clock clock=Clock.fixed(Instant.parse("2026-11-01T16:00:00Z"),ZoneOffset.UTC);

    @BeforeAll void initializeOnlyMarkedTestDatabase() throws Exception {
        dataSource=new DriverManagerDataSource("jdbc:mysql://127.0.0.1:33317/sagopalgo_account_observation_test"
            +"?allowPublicKeyRetrieval=true&useSSL=false&serverTimezone=UTC","root","observation-test-only");
        jdbc=new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject("SELECT DATABASE()",String.class)).isEqualTo("sagopalgo_account_observation_test");
        assertThat(jdbc.queryForObject("SELECT marker FROM isolated_test_environment_marker",String.class))
            .isEqualTo("SAGOPALGO_ISOLATED_ACCOUNT_OBSERVATION_TEST_ONLY");
        jdbc.execute("CREATE TABLE IF NOT EXISTS users(user_id BIGINT NOT NULL PRIMARY KEY) ENGINE=InnoDB");
        jdbc.update("INSERT IGNORE INTO users VALUES (1),(2)");
        migrate();
    }
    @BeforeEach void resetOnlyCollectorFixtures() throws Exception {
        jdbc.update("DELETE FROM kb_account_observation_collectors");jdbc.update("DELETE FROM kb_account_observations");
        properties=properties();binding=new AccountObservationBinding(properties);
        codec=new AccountObservationCodec(new ObjectMapper().findAndRegisterModules());
        observer=mock(KbAccountSnapshotService.class);when(observer.observe(DATE)).thenAnswer(c -> snapshot(Status.SUCCESS));
        var template=template();mapper=template.getMapper(AccountObservationCollectorMapper.class);
        collector=new AccountObservationCollectorStore(mapper,new DataSourceTransactionManager(dataSource));
        observations=new AccountObservationStore(template.getMapper(AccountObservationMapper.class),new DataSourceTransactionManager(dataSource));
        history=new AccountObservationHistoryService(observations,binding,observer,codec);
        service=worker(collector,true);
    }

    @Test void successfulCyclePersistsAndCooldownPreventsExtraBrokerRead() throws Exception {
        service.collectDue();var first=service.status(1L);
        assertThat(first.state()).isEqualTo("IDLE");assertThat(first.lastSnapshotStatus()).isEqualTo("SUCCESS");
        assertThat(history.detail(1L,first.lastRequestId()).storageState()).isEqualTo("COMPLETED");
        assertThat(jdbc.queryForObject("SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(6),next_due_at) FROM kb_account_observation_collectors",Integer.class))
            .isBetween(895,900);
        migrate();service.collectDue();worker(new AccountObservationCollectorStore(template().getMapper(AccountObservationCollectorMapper.class),
            new DataSourceTransactionManager(dataSource)),true).collectDue();
        verify(observer,times(1)).observe(DATE);assertThat(count("kb_account_observations")).isEqualTo(1);
    }

    @Test void eightIndependentWorkersShareOneDurableOwner() throws Exception {
        var barrier=new CyclicBarrier(8);var executor=Executors.newFixedThreadPool(8);var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        when(observer.observe(DATE)).thenAnswer(c -> {entered.countDown();if(!release.await(10,TimeUnit.SECONDS)) throw new AssertionError("timeout");return snapshot(Status.SUCCESS);});
        try {
            List<Future<?>> tasks=new ArrayList<>();
            for(int i=0;i<8;i++) {
                var independent=worker(new AccountObservationCollectorStore(template().getMapper(AccountObservationCollectorMapper.class),
                    new DataSourceTransactionManager(dataSource)),true);
                tasks.add(executor.submit(() -> {barrier.await(10,TimeUnit.SECONDS);independent.collectDue();return null;}));
            }
            assertThat(entered.await(10,TimeUnit.SECONDS)).isTrue();release.countDown();
            for(var task:tasks) task.get(20,TimeUnit.SECONDS);
        } finally {release.countDown();executor.shutdownNow();}
        verify(observer,times(1)).observe(DATE);assertThat(count("kb_account_observations")).isEqualTo(1);
        assertThat(count("kb_account_observation_collectors")).isEqualTo(1);assertThat(service.status(1L).state()).isEqualTo("IDLE");
    }

    @Test void claimCommitsBeforeObserverAndNoDbTransactionSpansNetworkRead() {
        when(observer.observe(DATE)).thenAnswer(c -> {
            assertThat(org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()).isFalse();
            var claim=collector.find(1L,binding.current());assertThat(claim.state()).isEqualTo("ACTIVE");
            assertThat(observations.find(1L,binding.current(),claim.activeRequestId()).storageState()).isEqualTo("PENDING");
            return snapshot(Status.SUCCESS);
        });
        service.collectDue();assertThat(service.status(1L).state()).isEqualTo("IDLE");verify(observer).observe(DATE);
    }

    @Test void orphanClaimBeforeObservationReservationNeverExpiresOrStartsNewRead() throws Exception {
        String id=id();collector.claim(1L,binding.current(),id,DATE);
        jdbc.update("UPDATE kb_account_observation_collectors SET started_at='2000-01-01',next_due_at='2000-01-01'");
        var recreated=worker(new AccountObservationCollectorStore(template().getMapper(AccountObservationCollectorMapper.class),new DataSourceTransactionManager(dataSource)),true);
        recreated.collectDue();recreated.collectDue();
        assertThat(recreated.status(1L).activeRequestId()).isEqualTo(id);assertThat(recreated.status(1L).state()).isEqualTo("ACTIVE");
        assertThat(count("kb_account_observations")).isZero();verifyNoInteractions(observer);
        assertError(() -> recreated.resume(1L,id),ErrorCode.DUPLICATE_RESOURCE);
    }

    @Test void pendingReceiptSurvivesRecreationAndOnlyStoredCompletionCanReleaseIt() throws Exception {
        String id=id();String scope=binding.current();collector.claim(1L,scope,id,DATE);observations.reserve(1L,id,scope,DATE,NOW);
        var recreated=worker(new AccountObservationCollectorStore(template().getMapper(AccountObservationCollectorMapper.class),new DataSourceTransactionManager(dataSource)),true);
        recreated.collectDue();assertThat(recreated.status(1L).state()).isEqualTo("ACTIVE");verifyNoInteractions(observer);
        var snapshot=snapshot(Status.SUCCESS);
        observations.complete(1L,id,scope,snapshot.observationId(),"SUCCESS",codec.encode(snapshot,DATE),NOW);
        recreated.collectDue();assertThat(recreated.status(1L).state()).isEqualTo("IDLE");
        assertThat(recreated.status(1L).lastRequestId()).isEqualTo(id);verifyNoInteractions(observer);
    }

    @Test void collectorFinishRollbackKeepsActiveButNextWorkerReadsCompletedReceiptOnly() {
        var failing=spy(mapper);
        doAnswer(c -> {
            mapper.finish(c.getArgument(0),c.getArgument(1),c.getArgument(2),c.getArgument(3),c.getArgument(4),
                c.getArgument(5),c.getArgument(6),c.getArgument(7),c.getArgument(8));
            throw new DataAccessResourceFailureException("private SQL");
        }).when(failing).finish(anyLong(),anyString(),anyString(),anyString(),anyString(),anyString(),any(),any(),anyInt());
        worker(new AccountObservationCollectorStore(failing,new DataSourceTransactionManager(dataSource)),true).collectDue();
        assertThat(service.status(1L).state()).isEqualTo("ACTIVE");
        String id=service.status(1L).activeRequestId();assertThat(history.detail(1L,id).storageState()).isEqualTo("COMPLETED");
        service.collectDue();assertThat(service.status(1L).lastRequestId()).isEqualTo(id);
        assertThat(service.status(1L).state()).isEqualTo("IDLE");verify(observer,times(1)).observe(DATE);
    }

    @Test void claimTransactionFailureRollsBackBeforeAnyObservation() {
        var failing=spy(mapper);doThrow(new DataAccessResourceFailureException("private SQL")).when(failing).find(anyLong(),anyString());
        worker(new AccountObservationCollectorStore(failing,new DataSourceTransactionManager(dataSource)),true).collectDue();
        assertThat(count("kb_account_observation_collectors")).isZero();assertThat(count("kb_account_observations")).isZero();verifyNoInteractions(observer);
    }

    @Test void partialSnapshotPausesAndExplicitResumeOnlySchedulesANewCycle() {
        when(observer.observe(DATE)).thenReturn(snapshot(Status.PARTIAL),snapshot(Status.SUCCESS));
        service.collectDue();var paused=service.status(1L);assertThat(paused.state()).isEqualTo("PAUSED");
        assertThat(paused.failureCode()).isEqualTo("SNAPSHOT_PARTIAL");service.collectDue();verify(observer,times(1)).observe(DATE);
        assertError(() -> service.resume(1L,id()),ErrorCode.DUPLICATE_RESOURCE);
        service.resume(1L,paused.lastRequestId());service.collectDue();verify(observer,times(1)).observe(DATE);
        dueNow();service.collectDue();var next=service.status(1L);
        assertThat(next.lastRequestId()).isNotEqualTo(paused.lastRequestId());assertThat(next.state()).isEqualTo("IDLE");
        assertThat(history.detail(1L,paused.lastRequestId()).snapshotStatus()).isEqualTo("PARTIAL");
        assertThat(count("kb_account_observations")).isEqualTo(2);verify(observer,times(2)).observe(DATE);
    }

    @Test void observerExceptionBecomesKnownFailedReceiptAndPausesCollection() {
        when(observer.observe(DATE)).thenThrow(new IllegalStateException("private KB"));
        service.collectDue();var paused=service.status(1L);
        assertThat(paused.state()).isEqualTo("PAUSED");assertThat(paused.lastStorageState()).isEqualTo("FAILED");
        assertThat(paused.lastSnapshotStatus()).isNull();assertThat(paused.failureCode()).isEqualTo("OBSERVATION_FAILED");
        service.collectDue();verify(observer,times(1)).observe(DATE);
    }

    @Test void stoppedConfigurationDoesNotReleaseOrResumeActiveRequest() {
        collector.claim(1L,binding.current(),id(),DATE);
        worker(collector,false).collectDue();assertThat(service.status(1L).state()).isEqualTo("ACTIVE");verifyNoInteractions(observer);
    }

    @Test void currentUserAndCredentialNamespacesAreIsolated() {
        when(observer.observe(DATE)).thenReturn(snapshot(Status.PARTIAL));service.collectDue();var first=service.status(1L);
        assertThat(service.status(2L).state()).isEqualTo("NOT_STARTED");assertError(() -> service.resume(2L,first.lastRequestId()),ErrorCode.DUPLICATE_RESOURCE);
        properties.getKb().setAppKey("new-private-key");assertThat(service.status(1L).state()).isEqualTo("NOT_STARTED");
        assertError(() -> service.resume(1L,first.lastRequestId()),ErrorCode.DUPLICATE_RESOURCE);
        assertThat(count("kb_account_observation_collectors")).isEqualTo(1);verify(observer,times(1)).observe(DATE);
    }

    @Test void tamperedCompletedReceiptCannotReleaseActiveOrResumePausedState() {
        String id=id(),scope=binding.current();collector.claim(1L,scope,id,DATE);
        var snapshot=snapshot(Status.PARTIAL);observations.reserve(1L,id,scope,DATE,NOW);
        observations.complete(1L,id,scope,snapshot.observationId(),"PARTIAL",codec.encode(snapshot,DATE),NOW);
        service.collectDue();assertThat(service.status(1L).state()).isEqualTo("PAUSED");
        jdbc.update("UPDATE kb_account_observations SET payload=REPLACE(payload,'0.123456','0.654321') WHERE request_id=?",id);
        assertError(() -> service.resume(1L,id),ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE);
        assertThat(service.status(1L).state()).isEqualTo("PAUSED");verifyNoInteractions(observer);
    }

    @Test void databaseCheckRejectsImpossibleStatesAndSqlNullBypass() {
        collector.claim(1L,binding.current(),id(),DATE);
        assertThatThrownBy(() -> jdbc.update("UPDATE kb_account_observation_collectors SET active_request_id=NULL")).isInstanceOf(DataAccessException.class);
        assertThatThrownBy(() -> jdbc.update("UPDATE kb_account_observation_collectors SET last_request_id=?,last_storage_state='COMPLETED',last_snapshot_status=NULL",id()))
            .isInstanceOf(DataAccessException.class);
        assertThat(service.status(1L).state()).isEqualTo("ACTIVE");
    }

    @Test void getStatusAndResumeHttpDoNotCallKbAndFixedRouteWinsOverDetail() throws Exception {
        when(observer.observe(DATE)).thenReturn(snapshot(Status.PARTIAL));service.collectDue();var paused=service.status(1L);
        var context=new LocalUserContext(new PersonalModeProperties(true,1L,"owner","local@test"));
        var mvc=MockMvcBuilders.standaloneSetup(new AccountObservationCollectionController(service,context),new AccountObservationHistoryController(history,context))
            .setControllerAdvice(new GlobalExceptionHandler()).build();
        String url="/api/v1/kb/accounts/primary/observations/collection";
        String body=mvc.perform(get(url)).andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
            .andExpect(jsonPath("$.data.state").value("PAUSED")).andExpect(jsonPath("$.data.usableForTrading").value(false))
            .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(body).doesNotContain(binding.current(),"private-key","private-secret","accountBinding","userId");
        mvc.perform(post(url+"/resume").contentType(MediaType.APPLICATION_JSON).content("{\"lastRequestId\":\""+paused.lastRequestId()+"\"}"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store")).andExpect(jsonPath("$.data.state").value("IDLE"));
        mvc.perform(post(url+"/resume").contentType(MediaType.APPLICATION_JSON).content("{}"))
            .andExpect(status().isBadRequest());
        verify(observer,times(1)).observe(DATE);assertThat(count("kb_account_observations")).isEqualTo(1);
    }

    private AccountObservationCollectionService worker(AccountObservationCollectorStore target,boolean enabled) {
        return new AccountObservationCollectionService(new AccountObservationCollectionProperties(enabled,900),
            new PersonalModeProperties(true,1L,"owner","local@test"),properties,binding,target,history,clock);
    }
    private SqlSessionTemplate template() throws Exception {
        var config=new Configuration();config.addMapper(AccountObservationMapper.class);config.addMapper(AccountObservationCollectorMapper.class);
        var factory=new SqlSessionFactoryBean();factory.setDataSource(dataSource);factory.setConfiguration(config);
        return new SqlSessionTemplate(factory.getObject());
    }
    private void migrate() throws Exception {
        try(var connection=dataSource.getConnection()) {
            for(String sql:List.of("023_account_observation_history.sql","024_account_observation_collection.sql"))
                ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/"+sql));
        }
    }
    private int count(String table) {
        if(!Set.of("kb_account_observations","kb_account_observation_collectors").contains(table)) throw new IllegalArgumentException();
        return jdbc.queryForObject("SELECT COUNT(*) FROM "+table,Integer.class);
    }
    private void dueNow() {jdbc.update("UPDATE kb_account_observation_collectors SET next_due_at='2000-01-01'");}
    private String id() {return UUID.randomUUID().toString();}
    private void assertError(Runnable action,ErrorCode code) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(code));
    }
}
