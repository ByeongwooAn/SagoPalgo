package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import static com.sagopalgo.api.kb.service.AccountObservationFixtures.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.exception.GlobalExceptionHandler;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.controller.AccountObservationHistoryController;
import com.sagopalgo.api.kb.controller.AccountObservationComparisonController;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse.ComparisonStatus;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse.Reason;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.mapper.AccountObservationMapper;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.nio.charset.StandardCharsets;
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
import org.springframework.transaction.support.TransactionTemplate;

/** 전용 루프백 DB 이름·마커를 검사한 격리 MySQL만 사용합니다. KB observer는 항상 mock입니다. */
@EnabledIfEnvironmentVariable(named="SAGOPALGO_ACCOUNT_OBSERVATION_MYSQL_TEST", matches="true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class AccountObservationMysqlIntegrationTest {
    private DriverManagerDataSource dataSource;
    private JdbcTemplate jdbc;
    private AccountObservationMapper mapper;
    private SecuritiesProviderProperties properties;
    private AccountObservationBinding binding;
    private AccountObservationCodec codec;
    private AccountObservationStore store;
    private AccountObservationHistoryService service;
    private KbAccountSnapshotService observer;

    @BeforeAll void initializeOnlyMarkedTestDatabase() throws Exception {
        dataSource = new DriverManagerDataSource(
            "jdbc:mysql://127.0.0.1:33317/sagopalgo_account_observation_test?allowPublicKeyRetrieval=true&useSSL=false&serverTimezone=UTC",
            "root","observation-test-only");
        jdbc = new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject("SELECT DATABASE()",String.class)).isEqualTo("sagopalgo_account_observation_test");
        assertThat(jdbc.queryForObject("SELECT marker FROM isolated_test_environment_marker",String.class))
            .isEqualTo("SAGOPALGO_ISOLATED_ACCOUNT_OBSERVATION_TEST_ONLY");
        jdbc.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT NOT NULL PRIMARY KEY) ENGINE=InnoDB");
        jdbc.update("INSERT IGNORE INTO users VALUES (1),(2)");
        migrate();
    }

    @BeforeEach void resetOnlyObservationFixture() throws Exception {
        jdbc.update("DELETE FROM kb_account_observations");
        properties = properties(); binding = new AccountObservationBinding(properties);
        codec = new AccountObservationCodec(new ObjectMapper().findAndRegisterModules());
        observer = mock(KbAccountSnapshotService.class);
        when(observer.observe(DATE)).thenAnswer(call -> snapshot(Status.SUCCESS));
        mapper = newMapper();
        store = new AccountObservationStore(mapper,new DataSourceTransactionManager(dataSource));
        service = new AccountObservationHistoryService(store,binding,observer,codec);
    }

    @Test void migrationCanBeAppliedAgainWithoutChangingStoredObservation() throws Exception {
        var first = service.capture(1L,id(),DATE); migrate();
        assertThat(service.detail(1L,first.requestId())).isEqualTo(first);
        assertThat(count()).isEqualTo(1);
    }

    @Test void duplicateRequestHasOneBrokerReadAndOneImmutableRow() {
        String request=id(); var first=service.capture(1L,request,DATE);
        var again=service.capture(1L,request,DATE);
        assertThat(again).isEqualTo(first); assertThat(count()).isEqualTo(1);
        verify(observer,times(1)).observe(DATE);
    }

    @Test void concurrentDuplicateRequestsHaveOneWinner() throws Exception {
        String request=id(); var start=new CyclicBarrier(8); var executor=Executors.newFixedThreadPool(8);
        try {
            List<Future<String>> tasks=new ArrayList<>();
            for(int i=0;i<8;i++) tasks.add(executor.submit(() -> {start.await(10,TimeUnit.SECONDS);
                return service.capture(1L,request,DATE).storageState();}));
            for(var task:tasks) assertThat(task.get(20,TimeUnit.SECONDS)).isIn("PENDING","COMPLETED");
        } finally {executor.shutdownNow();}
        assertThat(count()).isEqualTo(1); verify(observer,times(1)).observe(DATE);
        assertThat(service.detail(1L,request).storageState()).isEqualTo("COMPLETED");
    }

    @Test void duplicateInsideStaleOuterTransactionReadsFreshReservation() {
        String request=id();
        var outer=new TransactionTemplate(new DataSourceTransactionManager(dataSource));
        outer.execute(tx -> {
            assertThat(count()).isZero(); // 이 외부 RR 트랜잭션의 읽기 스냅샷을 먼저 고정합니다.
            try {
                CompletableFuture.runAsync(() -> service.capture(1L,request,DATE)).get(10,TimeUnit.SECONDS);
            } catch(Exception exception) {throw new AssertionError(exception);}
            assertThat(service.capture(1L,request,DATE).storageState()).isEqualTo("COMPLETED");
            return null;
        });
        verify(observer,times(1)).observe(DATE);
        assertThat(count()).isEqualTo(1);
    }

    @Test void newMapperAndServiceReadExactStoredDecimalsAfterRecreation() throws Exception {
        var first=service.capture(1L,id(),DATE);
        var restarted=new AccountObservationHistoryService(new AccountObservationStore(newMapper(),
            new DataSourceTransactionManager(dataSource)),new AccountObservationBinding(properties),observer,
            new AccountObservationCodec(new ObjectMapper().findAndRegisterModules()));
        var reloaded=restarted.detail(1L,first.requestId());
        assertThat(reloaded).isEqualTo(first);
        assertThat(reloaded.observation().sections().get(2).rows().get(0).fields())
            .containsEntry("hld_q_p6","0.123456").containsEntry("now_prc",null);
        verify(observer,times(1)).observe(DATE);
    }

    @Test void otherUserAndChangedConnectionCannotReadOldHistory() {
        String request=id();service.capture(1L,request,DATE);
        assertNotFound(() -> service.detail(2L,request));
        assertThat(service.history(2L,null,20).items()).isEmpty();
        properties.getKb().setAppKey("another-key");
        assertNotFound(() -> service.detail(1L,request));
        assertThat(service.history(1L,null,20).items()).isEmpty();
        assertThatThrownBy(() -> service.capture(1L,request,DATE)).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.DUPLICATE_RESOURCE));
        verify(observer,times(1)).observe(DATE);
    }

    @Test void sameRequestCannotChangeDayButDifferentUsersHaveSeparateIds() {
        String request=id();service.capture(1L,request,DATE);
        assertThatThrownBy(() -> service.capture(1L,request,"20261101")).isInstanceOf(ApiException.class);
        service.capture(2L,request,DATE); assertThat(count()).isEqualTo(2);
        assertThat(service.history(1L,null,20).items()).hasSize(1);
        assertThat(service.history(2L,null,20).items()).hasSize(1);
        verify(observer,times(2)).observe(DATE);
    }

    @Test void pendingReservationSurvivesAndDuplicateNeverRecaptures() {
        String request=id(); store.reserve(1L,request,binding.current(),DATE,NOW);
        var result=service.capture(1L,request,DATE);
        assertThat(result.storageState()).isEqualTo("PENDING"); assertThat(result.observation()).isNull();
        verifyNoInteractions(observer);
    }

    @Test void finalTransactionFailureRollsBackPayloadButKeepsCommittedReservation() {
        var failing=spy(mapper);
        doThrow(new DataAccessResourceFailureException("private SQL payload")).when(failing)
            .findScoped(anyLong(),anyString(),anyString());
        var failingService=new AccountObservationHistoryService(new AccountObservationStore(failing,
            new DataSourceTransactionManager(dataSource)),binding,observer,codec);
        String request=id();
        assertThatThrownBy(() -> failingService.capture(1L,request,DATE)).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        assertThat(service.detail(1L,request).storageState()).isEqualTo("PENDING");
        assertThat(jdbc.queryForObject("SELECT payload IS NULL FROM kb_account_observations",Boolean.class)).isTrue();
        service.capture(1L,request,DATE); verify(observer,times(1)).observe(DATE);
    }

    @Test void duplicateServerObservationCannotBeStoredForAnotherRequest() {
        var same=snapshot(Status.SUCCESS);when(observer.observe(DATE)).thenReturn(same);
        service.capture(1L,id(),DATE);String other=id();
        assertThatThrownBy(() -> service.capture(1L,other,DATE)).isInstanceOf(ApiException.class);
        assertThat(service.detail(1L,other).storageState()).isEqualTo("PENDING");
        service.capture(1L,other,DATE); verify(observer,times(2)).observe(DATE);
    }

    @Test void partialAndFailedQueryStatusesArePreservedAsCompletedObservations() {
        when(observer.observe(DATE)).thenReturn(snapshot(Status.PARTIAL),snapshot(Status.FAILED));
        var partial=service.capture(1L,id(),DATE);var failed=service.capture(1L,id(),DATE);
        assertThat(partial.storageState()).isEqualTo("COMPLETED"); assertThat(partial.snapshotStatus()).isEqualTo("PARTIAL");
        assertThat(failed.storageState()).isEqualTo("COMPLETED"); assertThat(failed.snapshotStatus()).isEqualTo("FAILED");
        assertThat(partial.observation().usableForTrading()).isFalse();
    }

    @Test void changedConnectionDiscardsPayloadAndStoresOnlyFailure() {
        String old=binding.current();String request=id();
        when(observer.observe(DATE)).thenAnswer(call -> {properties.getKb().setAppKey("changed-key");return snapshot(Status.SUCCESS);});
        var result=service.capture(1L,request,DATE);
        assertThat(result.failureCode()).isEqualTo("CONTEXT_CHANGED"); assertThat(result.observation()).isNull();
        assertThat(mapper.findScoped(1L,old,request).payload()).isNull();
        assertThat(service.history(1L,null,20).items()).isEmpty();
    }

    @Test void keysetPagesDoNotRepeatWhenNewObservationArrives() {
        for(int i=0;i<3;i++) service.capture(1L,id(),DATE);
        var first=service.history(1L,null,2); service.capture(1L,id(),DATE);
        var second=service.history(1L,first.nextBeforeId(),2);
        assertThat(first.items()).hasSize(2);assertThat(second.items()).hasSize(1);
        assertThat(second.items().get(0).requestId()).isNotIn(first.items().stream().map(i -> i.requestId()).toList());
        assertThat(second.nextBeforeId()).isNull();
    }

    @Test void validJsonTamperingFailsChecksumWithoutBrokerRead() {
        String request=id();service.capture(1L,request,DATE);
        jdbc.update("UPDATE kb_account_observations SET payload=REPLACE(payload,'0.123456','0.654321') WHERE request_id=?",request);
        assertThatThrownBy(() -> service.detail(1L,request)).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        verify(observer,times(1)).observe(DATE);
    }

    @Test void databaseRejectsImpossibleStateEvenWithSqlNullSemantics() {
        String request=id();store.reserve(1L,request,binding.current(),DATE,NOW);
        assertThatThrownBy(() -> jdbc.update("UPDATE kb_account_observations SET storage_state='COMPLETED',"
            + "observation_id=?,payload='{}',payload_sha256=?,completed_at=? WHERE request_id=?",
            id(),"a".repeat(64),NOW,request)).isInstanceOf(DataAccessException.class);
        assertThatThrownBy(() -> jdbc.update("UPDATE kb_account_observations SET storage_state='FAILED',"
            + "completed_at=? WHERE request_id=?",NOW,request)).isInstanceOf(DataAccessException.class);
        assertThat(service.detail(1L,request).storageState()).isEqualTo("PENDING");
    }

    @Test void httpPostAndStoredGetsKeepPrivateIdentityOutOfResponses() throws Exception {
        var context=new LocalUserContext(new PersonalModeProperties(true,1L,"owner","local@test"));
        var mvc=MockMvcBuilders.standaloneSetup(new AccountObservationHistoryController(service,context))
            .setControllerAdvice(new GlobalExceptionHandler()).build();
        String request=id();
        mvc.perform(post("/api/v1/kb/accounts/primary/observations").contentType(MediaType.APPLICATION_JSON)
            .content("{\"requestId\":\""+request+"\",\"orderDate\":\""+DATE+"\"}"))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
            .andExpect(jsonPath("$.data.storageState").value("COMPLETED"));
        String body=mvc.perform(get("/api/v1/kb/accounts/primary/observations/"+request))
            .andExpect(status().isOk()).andExpect(jsonPath("$.data.readOnly").value(true))
            .andExpect(jsonPath("$.data.observation.sections[2].rows[0].fields.hld_q_p6").value("0.123456"))
            .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        mvc.perform(get("/api/v1/kb/accounts/primary/observations")).andExpect(status().isOk())
            .andExpect(jsonPath("$.data.items.length()").value(1));
        assertThat(body).doesNotContain("private-key","private-secret",binding.current(),"payloadSha256","accountBinding","userId");
        verify(observer,times(1)).observe(DATE);
    }

    @Test void comparisonHttpReadsPersistedDecimalsWithoutBrokerCallsOrWrites() throws Exception {
        var before=AccountObservationComparisonFixtures.change(AccountObservationComparisonFixtures.observation(0),0,
            s -> AccountObservationComparisonFixtures.rows(s,AccountObservationComparisonFixtures.row("is_no","005930","gnrl_q","0.123456")));
        var after=AccountObservationComparisonFixtures.change(AccountObservationComparisonFixtures.observation(1),0,
            s -> AccountObservationComparisonFixtures.rows(s,AccountObservationComparisonFixtures.row("is_no","005930","gnrl_q","0.123457")));
        when(observer.observe(DATE)).thenReturn(before,after);
        var a=service.capture(1L,id(),DATE);var b=service.capture(1L,id(),DATE);
        var saved=jdbc.queryForList("SELECT * FROM kb_account_observations ORDER BY record_id");
        var context=new LocalUserContext(new PersonalModeProperties(true,1L,"owner","local@test"));
        var mvc=MockMvcBuilders.standaloneSetup(new AccountObservationHistoryController(service,context),
            new AccountObservationComparisonController(comparisonService(),context))
            .setControllerAdvice(new GlobalExceptionHandler()).build();
        String body=mvc.perform(get("/api/v1/kb/accounts/primary/observations/comparison")
            .param("beforeRequestId",a.requestId()).param("afterRequestId",b.requestId()))
            .andExpect(status().isOk()).andExpect(header().string("Cache-Control","no-store"))
            .andExpect(jsonPath("$.data.status").value("COMPARED"))
            .andExpect(jsonPath("$.data.sections[0].rowChanges[0].fields[0].numericDelta").value("0.000001"))
            .andExpect(jsonPath("$.data.readOnly").value(true)).andExpect(jsonPath("$.data.usableForTrading").value(false))
            .andReturn().getResponse().getContentAsString(StandardCharsets.UTF_8);
        assertThat(body).doesNotContain("private-key","private-secret",binding.current(),"payloadSha256","accountBinding","userId");
        assertThat(jdbc.queryForList("SELECT * FROM kb_account_observations ORDER BY record_id")).isEqualTo(saved);
        verify(observer,times(2)).observe(DATE);verifyNoMoreInteractions(observer);
    }

    @Test void comparisonUsesCurrentUserAndBindingForBothRecords() {
        when(observer.observe(DATE)).thenReturn(AccountObservationComparisonFixtures.observation(0),AccountObservationComparisonFixtures.observation(1),
            AccountObservationComparisonFixtures.observation(2));
        var a=service.capture(1L,id(),DATE);var b=service.capture(1L,id(),DATE);
        assertNotFound(() -> comparisonService().compare(2L,a.requestId(),b.requestId()));
        properties.getKb().setAppKey("changed-key");
        assertNotFound(() -> comparisonService().compare(1L,a.requestId(),b.requestId()));
        var newScope=service.capture(1L,id(),DATE);
        assertNotFound(() -> comparisonService().compare(1L,newScope.requestId(),b.requestId()));
        assertThat(count()).isEqualTo(3);verify(observer,times(3)).observe(DATE);
    }

    @Test void pendingComparisonDoesNotCaptureOrModifyStoredRequests() {
        String a=id();store.reserve(1L,a,binding.current(),DATE,NOW);
        when(observer.observe(DATE)).thenReturn(AccountObservationComparisonFixtures.observation(1));
        var b=service.capture(1L,id(),DATE);
        var result=comparisonService().compare(1L,a,b.requestId());
        assertThat(result.status()).isEqualTo(ComparisonStatus.BLOCKED);
        assertThat(result.sections()).allSatisfy(s -> assertThat(s.reasons()).contains(Reason.STORAGE_NOT_COMPLETED));
        assertThat(service.detail(1L,a).storageState()).isEqualTo("PENDING");
        assertThat(count()).isEqualTo(2);verify(observer,times(1)).observe(DATE);
    }

    @Test void comparisonDoesNotReturnChangesFromTamperedStoredPayload() {
        when(observer.observe(DATE)).thenReturn(AccountObservationComparisonFixtures.observation(0),AccountObservationComparisonFixtures.observation(1));
        var a=service.capture(1L,id(),DATE);var b=service.capture(1L,id(),DATE);
        jdbc.update("UPDATE kb_account_observations SET payload=REPLACE(payload,'SUCCESS','PARTIAL') WHERE request_id=?",b.requestId());
        assertThatThrownBy(() -> comparisonService().compare(1L,a.requestId(),b.requestId()))
            .isInstanceOfSatisfying(ApiException.class,e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE));
        verify(observer,times(2)).observe(DATE);assertThat(count()).isEqualTo(2);
    }

    @Test void comparisonReadsStoredScopesAndCanBlockOneSectionOnly() {
        var a=AccountObservationComparisonFixtures.observation(0);
        var b=AccountObservationComparisonFixtures.change(AccountObservationComparisonFixtures.observation(1),0,
            s -> AccountObservationComparisonFixtures.scope(s,Map.of("stockFilter","005930")));
        when(observer.observe(DATE)).thenReturn(a,b);
        var left=service.capture(1L,id(),DATE);var right=service.capture(1L,id(),DATE);
        var result=comparisonService().compare(1L,left.requestId(),right.requestId());
        assertThat(result.status()).isEqualTo(ComparisonStatus.PARTIAL);
        assertThat(result.sections().get(0).reasons()).contains(Reason.SCOPE_MISMATCH);
        assertThat(result.sections().get(1).status()).isEqualTo(ComparisonStatus.COMPARED);
        verify(observer,times(2)).observe(DATE);
    }

    private AccountObservationComparisonService comparisonService() {
        return new AccountObservationComparisonService(service,binding,new AccountObservationComparison());
    }

    private AccountObservationMapper newMapper() throws Exception {
        var config=new Configuration();config.addMapper(AccountObservationMapper.class);
        var factory=new SqlSessionFactoryBean();factory.setDataSource(dataSource);factory.setConfiguration(config);
        return new SqlSessionTemplate(factory.getObject()).getMapper(AccountObservationMapper.class);
    }

    private void migrate() throws Exception {
        try(var connection=dataSource.getConnection()) {
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/023_account_observation_history.sql"));
        }
    }

    private int count() {return jdbc.queryForObject("SELECT COUNT(*) FROM kb_account_observations",Integer.class);}
    private String id() {return UUID.randomUUID().toString();}
    private void assertNotFound(Runnable action) {
        assertThatThrownBy(action::run).isInstanceOfSatisfying(ApiException.class,
            e -> assertThat(e.getErrorCode()).isEqualTo(ErrorCode.RESOURCE_NOT_FOUND));
    }
}
