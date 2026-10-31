package com.sagopalgo.api.order.mapper;

import static org.assertj.core.api.Assertions.*;

import com.sagopalgo.api.order.model.ManualOrderCommand;
import com.sagopalgo.api.order.model.ManualOrderReconciliationPreparation;
import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import com.sagopalgo.api.order.service.*;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import static org.mockito.Mockito.*;
import com.sagopalgo.api.order.service.ManualOrderReconciliationStore;
import com.sagopalgo.api.order.simulation.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.*;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.SqlSessionTemplate;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.core.io.FileSystemResource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.init.ScriptUtils;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;

/** 고정 루프백 포트·테스트 DB·마커가 모두 맞는 임시 MySQL에서만 실행합니다. KB 클라이언트는 만들지 않습니다. */
@EnabledIfEnvironmentVariable(named = "SAGOPALGO_ORDER_MYSQL_TEST", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ManualOrderMysqlIntegrationTest {
    private JdbcTemplate jdbc;
    private ManualOrderMapper commands;
    private ManualOrderReconciliationMapper reconciliations;
    private ManualOrderStore store;
    private ManualOrderDispatchMapper dispatches;
    private ManualOrderDispatchService dispatchService;
    private OrderAccountBinding binding;
    private ManualOrderDiagnosticMapper diagnosticMapper;
    private ManualOrderDiagnosticStore diagnosticStore;
    private ManualOrderDiagnosticService diagnosticService;
    private KbOrderExecutionService diagnosticExecutions;
    private UnknownOrderReviewMapper reviewMapper;
    private UnknownOrderReviewStore reviewStore;
    private UnknownOrderReviewService reviewService;
    private ManualOrderReconciliationStore reconciliationStore;
    private DataSourceTransactionManager transactions;
    private OrderSimulationMapper simulations;
    private OrderSimulationStore simulationStore;
    private OrderSimulationService simulationService;
    private static final String FINGERPRINT = "f".repeat(64);
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");

    @BeforeAll void connectOnlyToIsolatedFixture() throws Exception {
        var dataSource = new DriverManagerDataSource(
            "jdbc:mysql://127.0.0.1:33316/sagopalgo_order_test?allowPublicKeyRetrieval=true&useSSL=false&serverTimezone=Asia/Seoul",
            "root", "order-test-only");
        jdbc = new JdbcTemplate(dataSource);
        assertThat(jdbc.queryForObject("SELECT DATABASE()", String.class)).isEqualTo("sagopalgo_order_test");
        assertThat(jdbc.queryForObject("SELECT marker FROM isolated_test_environment_marker", String.class))
            .isEqualTo("SAGOPALGO_ISOLATED_ORDER_TEST_ONLY");
        try (var connection = dataSource.getConnection()) {
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/schema.sql"));
            // 016을 실제 업그레이드와 같은 테이블 부재 상태에서 검증합니다.
            jdbc.execute("DROP TABLE IF EXISTS manual_order_reviews");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_review_preparations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_diagnostics");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_dispatch_recoveries");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_dispatches");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_reconciliations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_reconciliation_preparations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_observations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_commands");
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/016_manual_order_commands.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/017_manual_order_reconciliations.sql"));
            jdbc.execute("DROP TABLE IF EXISTS order_simulation_sessions");
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/018_order_simulation_sessions.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/018_order_simulation_sessions.sql"));
            // 재적용도 안전한 CREATE IF NOT EXISTS인지 검증합니다.
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/016_manual_order_commands.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/017_manual_order_reconciliations.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/019_manual_order_dispatch_journal.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/019_manual_order_dispatch_journal.sql"));
        }
        try(var connection=dataSource.getConnection()) {
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/020_manual_order_diagnostics.sql"));
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/020_manual_order_diagnostics.sql"));
        }
        try(var connection=dataSource.getConnection()){
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/021_unknown_order_reviews.sql"));
            ScriptUtils.executeSqlScript(connection,new FileSystemResource("../database/migrations/021_unknown_order_reviews.sql"));
        }
        var configuration = new Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.addMapper(ManualOrderMapper.class);
        configuration.addMapper(ManualOrderDispatchMapper.class);
        configuration.addMapper(ManualOrderDiagnosticMapper.class);
        configuration.addMapper(UnknownOrderReviewMapper.class);
        configuration.addMapper(OrderSubmissionGuardMapper.class);
        configuration.addMapper(ManualOrderReconciliationMapper.class);
        configuration.addMapper(OrderSimulationMapper.class);
        var factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setConfiguration(configuration);
        var session = new SqlSessionTemplate(factory.getObject());
        commands = session.getMapper(ManualOrderMapper.class);
        reconciliations = session.getMapper(ManualOrderReconciliationMapper.class);
        transactions = new DataSourceTransactionManager(dataSource);
        dispatches=session.getMapper(ManualOrderDispatchMapper.class);
        binding=mock(OrderAccountBinding.class);
        dispatchService=proxy(new ManualOrderDispatchService(commands,dispatches,binding));
        diagnosticMapper=session.getMapper(ManualOrderDiagnosticMapper.class);
        diagnosticExecutions=mock(KbOrderExecutionService.class);
        diagnosticStore=proxy(new ManualOrderDiagnosticStore(commands,dispatches,diagnosticMapper,binding,new ObjectMapper()));
        diagnosticService=new ManualOrderDiagnosticService(commands,diagnosticMapper,diagnosticStore,diagnosticExecutions,new ObjectMapper());
        reviewMapper=session.getMapper(UnknownOrderReviewMapper.class);
        reviewStore=proxy(new UnknownOrderReviewStore(commands,reviewMapper,binding));
        reviewService=new UnknownOrderReviewService(commands,reviewMapper,reviewStore,binding,diagnosticExecutions,new ObjectMapper());
        store = proxy(new ManualOrderStore(commands, session.getMapper(OrderSubmissionGuardMapper.class),dispatches));
        reconciliationStore = proxy(new ManualOrderReconciliationStore(commands, reconciliations));
        simulations = session.getMapper(OrderSimulationMapper.class);
        simulationStore = new OrderSimulationStore(simulations, new ObjectMapper(), transactions);
        simulationService = new OrderSimulationService(simulations, simulationStore, new ObjectMapper());
    }

    @SuppressWarnings("unchecked")
    private <T> T proxy(T target) {
        var factory = new ProxyFactory(target);
        factory.setProxyTargetClass(true);
        factory.addAdvice(new TransactionInterceptor(transactions, new AnnotationTransactionAttributeSource()));
        return (T) factory.getProxy();
    }

    @BeforeEach void resetOnlyIsolatedOrderTables() {
        when(binding.matches(FINGERPRINT)).thenReturn(true);
        reset(diagnosticExecutions);
        // 같은 테이블의 부모 FK는 DELETE 전체 실행 순서에도 적용됩니다. 격리 fixture의 참조만 먼저 끊습니다.
        jdbc.update("UPDATE manual_order_commands SET parent_id=NULL");
        for (String table : List.of("manual_order_reviews","manual_order_review_preparations","manual_order_diagnostics","manual_order_dispatch_recoveries","manual_order_dispatches","order_simulation_sessions", "manual_order_reconciliations", "manual_order_reconciliation_preparations",
            "manual_order_observations", "manual_order_commands", "order_submission_guards", "order_approvals", "order_prechecks")) {
            jdbc.update("DELETE FROM " + table);
        }
    }

    @Test void schemaConstraintsAndRecordMappingAreRealMysqlCompatible() {
        var command = command(approval(), "SENDING");
        store.claim(command);
        assertThat(commands.find(command.commandId(), 1L)).isEqualTo(command);
        assertThat(commands.find(command.commandId(), 2L)).isNull();
        assertThatThrownBy(() -> jdbc.update("UPDATE manual_order_commands SET kind='INVALID' WHERE command_id=?", command.commandId()))
            .isInstanceOf(org.springframework.dao.DataAccessException.class);
        assertThat(commands.verifyStorage()).isNotBlank();
    }

    @Test void simultaneousSameApprovalReservesExactlyOneCommand() throws Exception {
        long approval = approval();
        assertThat(race(() -> store.claim(command(approval, "SENDING")), () -> store.claim(command(approval, "SENDING"))))
            .containsExactlyInAnyOrder(true, false);
        assertThat(commands.pending(1L)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_commands", Integer.class)).isEqualTo(1);
    }

    @Test void differentApprovalsCannotBypassPendingTransmission() throws Exception {
        long first = approval(); long second = approval();
        assertThat(race(() -> store.claim(command(first, "SENDING")), () -> store.claim(command(second, "SENDING"))))
            .containsExactlyInAnyOrder(true, false);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM order_submission_guards WHERE status='READY'", Integer.class)).isEqualTo(1);
    }

    @Test void failedAuditInsertRollsBackActualGuardReservation() {
        var original = command(approval(), "REJECTED");
        commands.insert(original);
        long next = approval();
        var duplicateId = new ManualOrderCommand(original.commandId(), 1L, next, null, "NEW", "005930", "삼성전자",
            "KOSPI", "BUY", new BigDecimal("100.00"), new BigDecimal("1.0000"), FINGERPRINT, null, now().plusSeconds(90),
            "SENDING", null, "20261031", null, null, null, now(), now());
        assertThatThrownBy(() -> store.claim(duplicateId)).isInstanceOf(org.springframework.dao.DataAccessException.class);
        assertThat(jdbc.queryForObject("SELECT status FROM order_submission_guards WHERE order_approval_id=?", String.class, next)).isEqualTo("READY");
    }

    @Test void expiredGuardIsRejectedByMysqlPredicate() {
        long approval = approval();
        jdbc.update("UPDATE order_submission_guards SET expires_at=? WHERE order_approval_id=?", LocalDateTime.now().minusSeconds(1), approval);
        assertThatThrownBy(() -> store.claim(command(approval, "SENDING"))).isInstanceOf(RuntimeException.class);
        assertThat(commands.pending(1L)).isZero();
    }

    @Test void concurrentConfirmationConsumesExactlyOnceAndPreservesOriginalUnknown() throws Exception {
        var command = command(approval(), "SENDING");
        store.claim(command);
        commands.finish(command.commandId(), 1L, "UNKNOWN", "", "", "", now());
        var record = prepareResolution(command, "0040000638");
        assertThat(race(() -> reconciliationStore.confirm(record, "h".repeat(64), now()),
            () -> reconciliationStore.confirm(record, "h".repeat(64), now()))).containsExactlyInAnyOrder(true, false);
        assertThat(commands.find(command.commandId(), 1L).status()).isEqualTo("UNKNOWN");
        assertThat(commands.pending(1L)).isZero();
        assertThat(reconciliations.find(command.commandId(), 1L)).isEqualTo(record);
        assertThat(reconciliations.preparation(command.commandId(), 1L)).isNull();
        assertThat(jdbc.queryForObject("SELECT status FROM order_submission_guards WHERE order_approval_id=?",
            String.class, command.approvalId())).isEqualTo("RESERVED");
    }

    @Test void expiredReconciliationCannotConsumeTokenOrReleasePendingOrder() {
        var command = command(approval(), "UNKNOWN"); commands.insert(command);
        var record = prepareResolution(command, "0040000638");
        jdbc.update("UPDATE manual_order_reconciliation_preparations SET expires_at=? WHERE command_id=?",
            now().minusSeconds(1), command.commandId());
        assertThatThrownBy(() -> reconciliationStore.confirm(record, "h".repeat(64), now())).isInstanceOf(RuntimeException.class);
        assertThat(reconciliations.find(command.commandId(), 1L)).isNull();
        assertThat(reconciliations.preparation(command.commandId(), 1L)).isNotNull();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void reusedBrokerNumberRollsBackTokenConsumptionAndKeepsOtherOrderBlocked() {
        var first = command(approval(), "UNKNOWN"); var second = command(approval(), "UNKNOWN");
        commands.insert(first); commands.insert(second);
        reconciliationStore.confirm(prepareResolution(first, "0040000638"), "h".repeat(64), now());
        var duplicate = prepareResolution(second, "0040000638");
        assertThatThrownBy(() -> reconciliationStore.confirm(duplicate, "h".repeat(64), now()))
            .isInstanceOf(org.springframework.dao.DataAccessException.class);
        assertThat(reconciliations.preparation(second.commandId(), 1L)).isNotNull();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void simulationApprovalIsSeparateAndUsesHashOnlyInDatabase() {
        String id = simSession("1000000");
        var prepared = simulationService.prepare(1L,id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        String command = (String) prepared.get("commandId");
        assertThat(simCommand(simulationService.get(1L,id), command)).containsEntry("status","PREPARED").containsEntry("sendCount",0);
        assertThat(simulations.find(id,1L).stateJson()).contains("tokenHash").doesNotContain((String)prepared.get("token"));
        assertThat(simulationService.get(1L,id).toString()).doesNotContain("tokenHash").contains("SIMULATION");
        assertThatThrownBy(() -> simulationService.submit(1L,id,command,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        simulationService.confirm(1L,id,command,(String)prepared.get("token"),true);
        assertThatThrownBy(() -> simulationService.confirm(1L,id,command,(String)prepared.get("token"),true)).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> simulationService.submit(1L,id,command,true,"실제 주문 전송")).isInstanceOf(RuntimeException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM order_approvals",Integer.class)).isZero();
    }

    @Test void simulationWaitPartialFullAndSellUpdateOnlyVirtualAccount() {
        String id=simSession("1000000");
        String buy=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        var accepted=simulationService.submit(1L,id,buy,true,"모의 주문 전송");
        String number=(String)simCommand(accepted,buy).get("brokerOrderNo");
        assertThat((BigDecimal)accepted.get("availableCash")).isEqualByComparingTo("850000");
        var partial=simulationService.fill(1L,id,number,BigDecimal.ONE);
        assertThat(simCommand(partial,buy)).containsEntry("brokerStatus","PARTIAL");
        assertThat((BigDecimal)partial.get("cash")).isEqualByComparingTo("925000");
        simulationService.fill(1L,id,number,BigDecimal.ONE);
        String sell=simReady(id,simPlan("SELL","75000","2"),"NEW",null,"FULL_FILL");
        var done=simulationService.submit(1L,id,sell,true,"모의 주문 전송");
        assertThat((BigDecimal)done.get("cash")).isEqualByComparingTo("1000000");
        assertThat(((Map<?,?>)done.get("positions")).get("KOSPI:005930")).isEqualTo(new BigDecimal("0"));
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_commands",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM trade_records",Integer.class)).isZero();
    }

    @ParameterizedTest
    @ValueSource(strings={"WAIT","PARTIAL_FILL","FULL_FILL","REJECT","TIMEOUT_BEFORE_ACCEPT","TIMEOUT_AFTER_ACCEPT","SAVE_FAILURE"})
    void simulationFaultScenariosPersistSingleSendAndSurviveServiceRecreation(String scenario) {
        String id=simSession("1000000");
        String command=simReady(id,simPlan("BUY","75000","2"),"NEW",null,scenario);
        if (scenario.equals("SAVE_FAILURE")) assertThatThrownBy(() -> simulationService.submit(1L,id,command,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        else simulationService.submit(1L,id,command,true,"모의 주문 전송");
        var restarted=new OrderSimulationService(simulations,new OrderSimulationStore(simulations,new ObjectMapper(),transactions),new ObjectMapper());
        var result=restarted.get(1L,id);
        String expected=switch(scenario){case "REJECT"->"REJECTED";case "SAVE_FAILURE"->"SENDING";
            case "TIMEOUT_BEFORE_ACCEPT","TIMEOUT_AFTER_ACCEPT"->"UNKNOWN";default->"ACCEPTED";};
        assertThat(simCommand(result,command)).containsEntry("status",expected).containsEntry("sendCount",1);
        restarted.submit(1L,id,command,true,"모의 주문 전송");
        assertThat(simCommand(restarted.get(1L,id),command)).containsEntry("sendCount",1);
        if (List.of("UNKNOWN","SENDING").contains(expected)) {
            assertThat(result.get("blocked")).isEqualTo(true);
            String other=simReady(id,simPlan("BUY","75000","1"),"NEW",null,"WAIT");
            assertThatThrownBy(() -> restarted.submit(1L,id,other,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        }
        if (scenario.equals("TIMEOUT_BEFORE_ACCEPT")) assertThat(simCommand(result,command)).containsEntry("brokerStatus","NONE");
        if (scenario.equals("TIMEOUT_AFTER_ACCEPT")) {
            assertThat(simCommand(result,command)).containsEntry("brokerStatus","FILLED");
            assertThat((BigDecimal)result.get("cash")).isEqualByComparingTo("850000");
        }
    }

    @Test void simulationSimultaneousSameCommandCannotSendTwice() throws Exception {
        String id=simSession("1000000");String command=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        race(() -> simulationService.submit(1L,id,command,true,"모의 주문 전송"),()->simulationService.submit(1L,id,command,true,"모의 주문 전송"));
        var state=simulationService.get(1L,id);
        assertThat(simCommand(state,command)).containsEntry("sendCount",1);
        assertThat((BigDecimal)state.get("availableCash")).isEqualByComparingTo("850000");
    }

    @Test void simulationConcurrentDifferentCommandsCannotOverReserveCash() throws Exception {
        String id=simSession("200000");
        String a=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        String b=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        assertThat(race(() -> simulationService.submit(1L,id,a,true,"모의 주문 전송"),()->simulationService.submit(1L,id,b,true,"모의 주문 전송")))
            .containsExactlyInAnyOrder(true,false);
        assertThat((BigDecimal)simulationService.get(1L,id).get("availableCash")).isEqualByComparingTo("50000");
    }

    @Test void simulationCancelReleasesReservationEvenAfterQuoteDriftAndCannotRepeat() {
        String id=simSession("1000000");String root=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        var accepted=simulationService.submit(1L,id,root,true,"모의 주문 전송");
        String originalNo=(String)simCommand(accepted,root).get("brokerOrderNo");
        simulationService.quote(1L,id,"KOSPI","005930",BigDecimal.ONE);
        String cancel=simReady(id,simPlan("BUY","75000","2"),"CANCEL",root,"WAIT");
        var result=simulationService.submit(1L,id,cancel,true,"모의 주문 전송");
        assertThat(simCommand(result,root)).containsEntry("brokerStatus","CANCELLED").containsEntry("changed",true);
        assertThat((BigDecimal)result.get("availableCash")).isEqualByComparingTo("1000000");
        assertThatThrownBy(() -> simulationService.fill(1L,id,originalNo,BigDecimal.ONE)).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> simReady(id,simPlan("BUY","75000","2"),"CANCEL",root,"WAIT")).isInstanceOf(RuntimeException.class);
    }

    @Test void simulationAmendReplacesOriginalAndPartialFillBlocksChanges() {
        String id=simSession("1000000");String root=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.submit(1L,id,root,true,"모의 주문 전송");
        String amend=simReady(id,simPlan("BUY","74000","2"),"AMEND",root,"WAIT");
        var result=simulationService.submit(1L,id,amend,true,"모의 주문 전송");
        assertThat(simCommand(result,root)).containsEntry("brokerStatus","REPLACED");
        assertThat((BigDecimal)result.get("availableCash")).isEqualByComparingTo("852000");
        String id2=simSession("1000000");String partial=simReady(id2,simPlan("BUY","75000","2"),"NEW",null,"PARTIAL_FILL");
        simulationService.submit(1L,id2,partial,true,"모의 주문 전송");
        assertThatThrownBy(() -> simReady(id2,simPlan("BUY","75000","2"),"CANCEL",partial,"WAIT")).isInstanceOf(RuntimeException.class);
    }

    @Test void simulationFreshQuoteExpiryAndStockAvailabilityBlockBeforeSend() {
        String id=simSession("1000000");
        assertThatThrownBy(() -> simReady(id,simPlan("SELL","75000","1"),"NEW",null,"WAIT")).isInstanceOf(RuntimeException.class);
        String command=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.quote(1L,id,"KOSPI","005930",new BigDecimal("100000"));
        assertThatThrownBy(() -> simulationService.submit(1L,id,command,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        assertThat(simCommand(simulationService.get(1L,id),command)).containsEntry("sendCount",0).containsEntry("status","READY");
        simulationService.quote(1L,id,"KOSPI","005930",new BigDecimal("75000"));
        simulationStore.mutate(1L,id,state->{state.commands.get(command).expiresAt=now().minusSeconds(1).toString();return null;});
        assertThatThrownBy(() -> simulationService.submit(1L,id,command,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
    }

    @ParameterizedTest @ValueSource(strings={"BUY","SELL"})
    void increasedPricePreservesQuantityReplacesOnceAndSettlesOnlyAtNewPrice(String side) {
        String id=simSession("BUY".equals(side)?"302000":"1000000");
        if("SELL".equals(side)) {
            String bought=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"FULL_FILL");simulationService.submit(1L,id,bought,true,"모의 주문 전송");
        }
        String parent=simReady(id,simPlan(side,"75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,id,parent,true,"모의 주문 전송");
        String child=simReady(id,simPlan(side,"76000","2"),"AMEND",parent,"WAIT");
        var changed=simulationService.submit(1L,id,child,true,"모의 주문 전송");
        assertThat(simCommand(changed,parent)).containsEntry("brokerStatus","REPLACED").containsEntry("changed",true);
        assertThat(simCommand(changed,child)).containsEntry("sendCount",1).containsEntry("brokerStatus","OPEN");
        assertThat((BigDecimal)changed.get("availableCash")).isEqualByComparingTo("BUY".equals(side)?"150000":"850000");
        assertThatThrownBy(()->simReady(id,simPlan(side,"77000","2"),"AMEND",parent,"WAIT")).isInstanceOf(RuntimeException.class);
        simulationService.submit(1L,id,child,true,"모의 주문 전송");
        String number=(String)simCommand(changed,child).get("brokerOrderNo");var settled=simulationService.fill(1L,id,number,new BigDecimal("2"));
        assertThat(simCommand(settled,child)).containsEntry("sendCount",1).containsEntry("brokerStatus","FILLED");
        assertThat((BigDecimal)settled.get("cash")).isEqualByComparingTo("BUY".equals(side)?"150000":"1002000");
        assertThat((BigDecimal)((Map<?,?>)settled.get("positions")).get("KOSPI:005930")).isEqualByComparingTo("BUY".equals(side)?"2":"0");
    }
    @Test void increasedBuyCannotBorrowOriginalReservationOrUseOnlyPriceDelta() {
        String id=simSession("301999");String parent=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.submit(1L,id,parent,true,"모의 주문 전송");
        String before=simulations.find(id,1L).stateJson();
        assertThatThrownBy(()->simReady(id,simPlan("BUY","76000","2"),"AMEND",parent,"WAIT")).isInstanceOf(RuntimeException.class);
        assertThat(simulations.find(id,1L).stateJson()).isEqualTo(before);
        assertThat(simCommand(simulationService.get(1L,id),parent)).containsEntry("changed",false);
        // 현금이 충분하지 않아도 기존 예약 범위 내의 가격 인하는 계속 허용합니다.
        assertThat(simReady(id,simPlan("BUY","74000","2"),"AMEND",parent,"WAIT")).isNotBlank();
    }
    @Test void cashConsumedAfterApprovalBlocksIncreaseBeforeClaimAndLeavesParentUsable() {
        String id=simSession("400000");String parent=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.submit(1L,id,parent,true,"모의 주문 전송");String child=simReady(id,simPlan("BUY","76000","2"),"AMEND",parent,"WAIT");
        String competing=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,id,competing,true,"모의 주문 전송");
        assertThatThrownBy(()->simulationService.submit(1L,id,child,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        var result=simulationService.get(1L,id);assertThat(simCommand(result,child)).containsEntry("status","READY").containsEntry("sendCount",0);
        assertThat(simCommand(result,parent)).containsEntry("changed",false).containsEntry("brokerStatus","OPEN");
        assertThat((BigDecimal)result.get("availableCash")).isEqualByComparingTo("100000");
        assertThat(simReady(id,simPlan("BUY","75000","2"),"CANCEL",parent,"WAIT")).isNotBlank();
    }
    @Test void concurrentPriceIncreasesConsumeOriginalOnce() throws Exception {
        String id=simSession("1000000");String parent=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,id,parent,true,"모의 주문 전송");
        String a=simReady(id,simPlan("BUY","76000","2"),"AMEND",parent,"WAIT"),b=simReady(id,simPlan("BUY","77000","2"),"AMEND",parent,"WAIT");
        assertThat(race(()->simulationService.submit(1L,id,a,true,"모의 주문 전송"),()->simulationService.submit(1L,id,b,true,"모의 주문 전송"))).containsExactlyInAnyOrder(true,false);
        var state=simulationService.get(1L,id);assertThat((int)simCommand(state,a).get("sendCount")+(int)simCommand(state,b).get("sendCount")).isEqualTo(1);
        var stored=simulationStore.decode(simulations.find(id,1L).stateJson());assertThat(stored.brokerOrders).hasSize(2);
        assertThat((BigDecimal)state.get("availableCash")).isBetween(new BigDecimal("846000"),new BigDecimal("848000"));
    }
    @Test void increasedAmendmentWithLostResponseCanResolveWithoutAdditionalSettlement() {
        String session=simSession("1000000");String parent=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,session,parent,true,"모의 주문 전송");
        String child=simReady(session,simPlan("BUY","76000","2"),"AMEND",parent,"TIMEOUT_AFTER_ACCEPT");var before=simulationService.submit(1L,session,child,true,"모의 주문 전송");
        var prepared=simulationService.prepareCompletion(1L,session,child,"0000000002");
        var after=simulationService.confirmCompletion(1L,session,child,(String)prepared.get("resolutionId"),(String)prepared.get("token"),true,"가상 주문 종결 확정");
        assertThat(after.get("blocked")).isEqualTo(false);assertThat(simCommand(after,child)).containsEntry("status","UNKNOWN").containsEntry("sendCount",1).containsEntry("resolved",true);
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));assertThat(after.get("positions")).isEqualTo(before.get("positions"));
        assertThat((BigDecimal)after.get("cash")).isEqualByComparingTo("848000");
    }
    @Test void unchangedOrOutOfRangeAmendPriceAndFreshQuoteChangeNeverSend() {
        String session=simSession("1000000");String parent=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,session,parent,true,"모의 주문 전송");
        for(String price:List.of("75000","0","75000.5","79000","1000000000")) {
            assertThatThrownBy(()->simReady(session,simPlan("BUY",price,"2"),"AMEND",parent,"WAIT")).isInstanceOf(RuntimeException.class);
        }
        String child=simReady(session,simPlan("BUY","76000","2"),"AMEND",parent,"WAIT");simulationService.quote(1L,session,"KOSPI","005930",new BigDecimal("100000"));
        assertThatThrownBy(()->simulationService.submit(1L,session,child,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        var result=simulationService.get(1L,session);assertThat(simCommand(result,child)).containsEntry("sendCount",0).containsEntry("status","READY");
        assertThat(simCommand(result,parent)).containsEntry("changed",false);
    }

    @Test void simulationOwnershipAndSessionIsolationDoNotTouchRealOrders() {
        String id=simSession("1000000");String c=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"TIMEOUT_AFTER_ACCEPT");
        simulationService.submit(1L,id,c,true,"모의 주문 전송");
        assertThatThrownBy(() -> simulationService.get(2L,id)).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(() -> simulationService.fill(2L,id,"0000000001",BigDecimal.ONE)).isInstanceOf(RuntimeException.class);
        String fresh=simSession("2000000");
        assertThat(simulationService.get(1L,id).get("blocked")).isEqualTo(true);
        assertThat(simulationService.get(1L,fresh).get("blocked")).isEqualTo(false);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_commands",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM order_approvals",Integer.class)).isZero();
    }

    @Test void receiptCommitsBeforeFailedFinalUpdateAndCanBeRecoveredAfterRestart() {
        var c=command(approval(),"SENDING"); String key=UUID.randomUUID().toString(); store.claim(c,key);
        dispatchService.begin(c,key);
        dispatchService.recordOutcome(c,key,accepted());
        // 실제 상태 UPDATE가 DB에서 실패해도 이미 커밋한 반환 결과는 보존됩니다.
        jdbc.execute("CREATE TRIGGER reject_dispatch_finish BEFORE UPDATE ON manual_order_commands FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test finish failure'");
        try { assertThatThrownBy(()->dispatchService.complete(1L,c.commandId())).isInstanceOf(RuntimeException.class); }
        finally { jdbc.execute("DROP TRIGGER reject_dispatch_finish"); }
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("SENDING");
        var restarted=proxy(new ManualOrderDispatchService(commands,dispatches,binding));
        assertThat(restarted.status(1L,c.commandId()).recoverable()).isTrue();
        assertThat(restarted.status(1L,c.commandId()).receipt().toString()).doesNotContain("private message");
        restarted.recover(1L,c.commandId(),true,"저장된 전송 결과 복구");
        restarted.recover(1L,c.commandId(),true,"저장된 전송 결과 복구");
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("ACCEPTED");
        assertThat(commands.pending(1L)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_dispatch_recoveries",Integer.class)).isEqualTo(1);
        assertThat(jdbc.queryForObject("SELECT status FROM order_submission_guards WHERE order_approval_id=?",String.class,c.approvalId())).isEqualTo("RESERVED");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM trade_records",Integer.class)).isZero();
    }

    @Test void activeMissingAndLegacyJournalsStayBlockedRegardlessOfAge() {
        var c=command(approval(),"SENDING"); String key="execution";store.claim(c,key);
        jdbc.update("UPDATE manual_order_dispatches SET reserved_at=? WHERE command_id=?",now().minusDays(2),c.commandId());
        assertThat(dispatchService.status(1L,c.commandId()).phase()).isEqualTo("RESERVED");
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        dispatchService.begin(c,key);
        assertThat(dispatchService.status(1L,c.commandId()).phase()).isEqualTo("DISPATCHING");
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        jdbc.update("DELETE FROM manual_order_dispatches WHERE command_id=?",c.commandId());
        assertThat(dispatchService.status(1L,c.commandId()).phase()).isEqualTo("LEGACY_UNVERIFIED");
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void wrongExecutionKeyCannotStartOrOverwriteImmutableReturnReceipt() {
        var c=command(approval(),"SENDING");store.claim(c,"owner");
        assertThatThrownBy(()->dispatchService.begin(c,"late-worker")).isInstanceOf(RuntimeException.class);
        dispatchService.begin(c,"owner");
        assertThatThrownBy(()->dispatchService.recordOutcome(c,"late-worker",accepted())).isInstanceOf(RuntimeException.class);
        dispatchService.recordOutcome(c,"owner",accepted());
        dispatchService.recordOutcome(c,"owner",accepted());
        assertThatThrownBy(()->dispatchService.recordOutcome(c,"owner",unknown())).isInstanceOf(RuntimeException.class);
        assertThat(dispatches.find(c.commandId(),1L).receipt().status()).isEqualTo("ACCEPTED");
    }

    @Test void recoveryRequiresOwnerCurrentAccountAndExplicitAcknowledgment() {
        var c=command(approval(),"SENDING");store.claim(c,"owner");dispatchService.begin(c,"owner");dispatchService.recordOutcome(c,"owner",accepted());
        assertThatThrownBy(()->dispatchService.recover(2L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->dispatchService.status(2L,c.commandId())).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),false,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"실제 주문 전송")).isInstanceOf(RuntimeException.class);
        when(binding.matches(FINGERPRINT)).thenReturn(false);
        assertThat(dispatchService.status(1L,c.commandId()).recoverable()).isFalse();
        assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void unknownReceiptRecoveryKeepsPendingGuardAndNeverInventsOrderNumber() {
        var c=command(approval(),"SENDING");store.claim(c,"owner");dispatchService.begin(c,"owner");dispatchService.recordOutcome(c,"owner",unknown());
        dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구");
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("UNKNOWN");
        assertThat(commands.find(c.commandId(),1L).orderNo()).isEmpty();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void resultApplicationAndConcurrentRecoveryAreIdempotent() throws Exception {
        var c=command(approval(),"SENDING");store.claim(c,"owner");dispatchService.begin(c,"owner");dispatchService.recordOutcome(c,"owner",accepted());
        assertThat(race(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구"),
            ()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구"))).containsOnly(true);
        dispatchService.complete(1L,c.commandId());
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_dispatch_recoveries",Integer.class)).isEqualTo(1);
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("ACCEPTED");
    }

    @Test void normalCompletionRacingRecoveryAppliesExactlyOnce() throws Exception {
        var c=command(approval(),"SENDING");store.claim(c,"owner");dispatchService.begin(c,"owner");dispatchService.recordOutcome(c,"owner",accepted());
        assertThat(race(()->dispatchService.complete(1L,c.commandId()),
            ()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구"))).containsOnly(true);
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("ACCEPTED");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_dispatch_recoveries",Integer.class)).isBetween(0,1);
    }

    @Test void failedRecoveryAuditRollsBackMainStateWithoutLosingReceipt() {
        var c=command(approval(),"SENDING");store.claim(c,"owner");dispatchService.begin(c,"owner");dispatchService.recordOutcome(c,"owner",accepted());
        jdbc.execute("CREATE TRIGGER reject_recovery_audit BEFORE INSERT ON manual_order_dispatch_recoveries FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test audit failure'");
        try {assertThatThrownBy(()->dispatchService.recover(1L,c.commandId(),true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);}
        finally {jdbc.execute("DROP TRIGGER reject_recovery_audit");}
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("SENDING");
        assertThat(dispatchService.status(1L,c.commandId()).recoverable()).isTrue();
    }

    @Test void failedDispatchReservationRollsBackGuardAndCommand() {
        var c=command(approval(),"SENDING");
        jdbc.execute("CREATE TRIGGER reject_dispatch_reservation BEFORE INSERT ON manual_order_dispatches FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test reservation failure'");
        try {assertThatThrownBy(()->store.claim(c,"owner")).isInstanceOf(RuntimeException.class);}
        finally {jdbc.execute("DROP TRIGGER reject_dispatch_reservation");}
        assertThat(commands.find(c.commandId(),1L)).isNull();
        assertThat(jdbc.queryForObject("SELECT status FROM order_submission_guards WHERE order_approval_id=?",String.class,c.approvalId())).isEqualTo("READY");
    }

    @Test void simulationSaveFailureRecoveryPreservesBrokerSendCountCashAndPositions() throws Exception {
        String id=simSession("1000000");String c=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"SAVE_FAILURE");
        assertThatThrownBy(()->simulationService.submit(1L,id,c,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        var before=simulationService.get(1L,id);
        assertThat(simCommand(before,c)).containsEntry("dispatchPhase","RETURNED").containsEntry("recoverable",true);
        assertThat(before.toString()).doesNotContain("executionKey","tokenHash");
        assertThatThrownBy(()->simulationService.recover(1L,id,c,false,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        assertThat(race(()->simulationService.recover(1L,id,c,true,"저장된 전송 결과 복구"),
            ()->simulationService.recover(1L,id,c,true,"저장된 전송 결과 복구"))).containsOnly(true);
        var after=simulationService.get(1L,id);
        assertThat(simCommand(after,c)).containsEntry("status","ACCEPTED").containsEntry("sendCount",1).containsEntry("recoverable",false);
        assertThat(after.get("blocked")).isEqualTo(false);
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));
        assertThat(after.get("positions")).isEqualTo(before.get("positions"));
        assertThat(((List<?>)after.get("events")).stream().filter(e->e.toString().contains("복구. 추가 전송")).count()).isEqualTo(1);
    }

    @ParameterizedTest @ValueSource(strings={"STOP_BEFORE_SEND","JOURNAL_FAILURE"})
    void simulationWithoutReturnedReceiptCannotRecoverOrResubmit(String scenario) {
        String id=simSession("1000000");String c=simReady(id,simPlan("BUY","75000","2"),"NEW",null,scenario);
        assertThatThrownBy(()->simulationService.submit(1L,id,c,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        int sends="STOP_BEFORE_SEND".equals(scenario)?0:1;
        assertThat(simCommand(simulationService.get(1L,id),c)).containsEntry("status","SENDING").containsEntry("recoverable",false).containsEntry("sendCount",sends);
        assertThatThrownBy(()->simulationService.recover(1L,id,c,true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
        simulationService.submit(1L,id,c,true,"모의 주문 전송");
        assertThat(simCommand(simulationService.get(1L,id),c)).containsEntry("sendCount",sends);
        assertThat(simulationService.get(1L,id).get("blocked")).isEqualTo(true);
    }

    @Test void legacySimulationJsonDoesNotInventRecoveryEvidence() {
        String id=simSession("1000000");String c=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"SAVE_FAILURE");
        simulationStore.mutate(1L,id,state->{state.commands.get(c).status="SENDING";return null;});
        assertThat(simCommand(simulationService.get(1L,id),c)).containsEntry("dispatchPhase","LEGACY_UNVERIFIED").containsEntry("recoverable",false);
        assertThatThrownBy(()->simulationService.recover(1L,id,c,true,"저장된 전송 결과 복구")).isInstanceOf(RuntimeException.class);
    }

    @ParameterizedTest @ValueSource(strings={"AMEND","CANCEL"})
    void changeReceiptRecoveryDoesNotReleaseOriginalChangeGuard(String kind) {
        var parent=command(approval(),"SENDING");store.claim(parent,"parent-worker");
        commands.finish(parent.commandId(),1L,"ACCEPTED","0040000638","200","A",now());
        var t=now();
        var child=new ManualOrderCommand(UUID.randomUUID().toString(),1L,null,parent.commandId(),kind,parent.stockCode(),parent.stockName(),
            parent.market(),parent.side(),new BigDecimal("99.00"),parent.quantity(),FINGERPRINT,"hash",t.plusSeconds(90),"PREPARED",null,parent.orderDate(),null,null,null,t,t);
        commands.insert(child);store.claim(child,"child-worker");dispatchService.begin(child,"child-worker");dispatchService.recordOutcome(child,"child-worker",accepted());
        dispatchService.recover(1L,child.commandId(),true,"저장된 전송 결과 복구");
        assertThat(commands.find(child.commandId(),1L).status()).isEqualTo("ACCEPTED");
        assertThat(commands.find(parent.commandId(),1L).changeId()).isEqualTo(child.commandId());
        assertThat(commands.find(parent.commandId(),1L).status()).isEqualTo("ACCEPTED");
    }

    @ParameterizedTest @ValueSource(strings={"AMEND","CANCEL"})
    void simulationChangeRecoveryAppliesReceiptWithoutChangingVirtualBrokerAgain(String kind) {
        String id=simSession("1000000");String parent=simReady(id,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.submit(1L,id,parent,true,"모의 주문 전송");
        String child=simReady(id,simPlan("BUY","74000","2"),kind,parent,"SAVE_FAILURE");
        assertThatThrownBy(()->simulationService.submit(1L,id,child,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        var before=simulationService.get(1L,id);
        var after=simulationService.recover(1L,id,child,true,"저장된 전송 결과 복구");
        assertThat(simCommand(after,child)).containsEntry("status","ACCEPTED").containsEntry("sendCount",1);
        assertThat(simCommand(after,parent)).isEqualTo(simCommand(before,parent));
        assertThat(after.get("availableCash")).isEqualTo(before.get("availableCash"));
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));
        assertThatThrownBy(()->simReady(id,simPlan("BUY","74000","2"),kind,parent,"WAIT")).isInstanceOf(RuntimeException.class);
    }

    private KbLimitOrderContract.Outcome accepted() {return new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","A","private message");}
    private KbLimitOrderContract.Outcome unknown() {return new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.UNKNOWN,"","","","");}

    @ParameterizedTest @ValueSource(strings={"RESERVED","DISPATCHING","LEGACY_UNVERIFIED"})
    void sendingDiagnosticsPersistReadOnlyObservationWithoutUnlocking(String phase) {
        var c=diagnosticCandidate(phase);var before=commands.find(c.commandId(),1L);var journal=dispatches.find(c.commandId(),1L);
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(diagnosticLookup(c));
        String id=UUID.randomUUID().toString();
        var response=diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단");
        assertThat(response.state()).isEqualTo("COMPLETED");assertThat(response.report().assessment()).isEqualTo("FIELDS_MATCH");
        assertThat(response.report().phaseAfter()).isEqualTo(phase);assertThat(response.report().commandStatusAfter()).isEqualTo("SENDING");
        assertThat(response.toString()).doesNotContain(FINGERPRINT,"private-name","private-reason");
        assertThat(commands.find(c.commandId(),1L)).isEqualTo(before);
        assertThat(dispatches.find(c.commandId(),1L)).isEqualTo(journal);
        assertThat(commands.pending(1L)).isEqualTo(1);
        assertThat(diagnosticService.history(1L,c.commandId())).hasSize(1);
        var restarted=new ManualOrderDiagnosticService(commands,diagnosticMapper,diagnosticStore,diagnosticExecutions,new ObjectMapper());
        assertThat(restarted.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isEqualTo(response);
        verify(diagnosticExecutions,times(1)).findByOrderNumber(c.orderDate(),"0040000638");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_reconciliations",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM trade_records",Integer.class)).isZero();
    }

    @Test void requestedDiagnosticSurvivesCrashAndNeverAutomaticallyQueriesAgain() {
        var c=diagnosticCandidate("RESERVED");String id=UUID.randomUUID().toString();
        diagnosticStore.claim(1L,c.commandId(),id,"0040000638");
        assertThat(diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단").state()).isEqualTo("REQUESTED");
        assertThat(diagnosticService.history(1L,c.commandId()).get(0).report()).isNull();
        assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000639",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        verifyNoInteractions(diagnosticExecutions);
    }

    @Test void concurrentSameDiagnosticIdHasAtMostOneReadAndCommittedRequestBeforeLookup() throws Exception {
        var c=diagnosticCandidate("DISPATCHING");String id=UUID.randomUUID().toString();
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var executor=Executors.newSingleThreadExecutor();
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenAnswer(call->{
            assertThat(diagnosticMapper.find(id,1L).state()).isEqualTo("REQUESTED");entered.countDown();
            if(!release.await(10,TimeUnit.SECONDS)) throw new IllegalStateException("test timeout");return diagnosticLookup(c);
        });
        try {
            var running=executor.submit(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단"));
            assertThat(entered.await(10,TimeUnit.SECONDS)).isTrue();
            assertThat(diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단").state()).isEqualTo("REQUESTED");
            release.countDown();assertThat(running.get(10,TimeUnit.SECONDS).state()).isEqualTo("COMPLETED");
        } finally {release.countDown();executor.shutdownNow();}
        verify(diagnosticExecutions,times(1)).findByOrderNumber(c.orderDate(),"0040000638");
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void diagnosticLookupFailureIsSanitizedAndRecordedWithoutStateChanges() {
        var c=diagnosticCandidate("DISPATCHING");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenThrow(new IllegalStateException("private-key-account"));
        var response=diagnosticService.diagnose(1L,c.commandId(),UUID.randomUUID().toString(),"0040000638",true,"잠금 유지 진단");
        assertThat(response.report().assessment()).isEqualTo("LOOKUP_FAILED");assertThat(response.toString()).doesNotContain("private-key-account");
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void accountChangedDuringLookupSuppressesBrokerObservation() {
        var c=diagnosticCandidate("DISPATCHING");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenAnswer(call->{when(binding.matches(FINGERPRINT)).thenReturn(false);return diagnosticLookup(c);});
        var response=diagnosticService.diagnose(1L,c.commandId(),UUID.randomUUID().toString(),"0040000638",true,"잠금 유지 진단");
        assertThat(response.report().assessment()).isEqualTo("ACCOUNT_CHANGED");assertThat(response.report().observation()).isNull();
        assertThat(response.report().checks()).isEmpty();assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void workerFinishingDuringDiagnosisIsObservedButNeverOverwritten() {
        var c=diagnosticCandidate("DISPATCHING");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenAnswer(call->{
            dispatchService.recordOutcome(c,"worker",accepted());dispatchService.complete(1L,c.commandId());return diagnosticLookup(c);
        });
        var response=diagnosticService.diagnose(1L,c.commandId(),UUID.randomUUID().toString(),"0040000638",true,"잠금 유지 진단");
        assertThat(response.report().phaseAfter()).isEqualTo("RETURNED");assertThat(response.report().commandStatusAfter()).isEqualTo("ACCEPTED");
        assertThat(commands.find(c.commandId(),1L).status()).isEqualTo("ACCEPTED");
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_dispatch_recoveries",Integer.class)).isZero();
    }

    @Test void invalidAckWrongOwnerChangedAccountAndReturnedReceiptCannotTriggerLookup() {
        var c=diagnosticCandidate("RESERVED");String id=UUID.randomUUID().toString();
        assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",false,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->diagnosticService.diagnose(2L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->diagnosticService.history(2L,c.commandId())).isInstanceOf(RuntimeException.class);
        when(binding.matches(FINGERPRINT)).thenReturn(false);
        assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        when(binding.matches(FINGERPRINT)).thenReturn(true);dispatchService.begin(c,"worker");dispatchService.recordOutcome(c,"worker",accepted());
        assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        verifyNoInteractions(diagnosticExecutions);
    }

    @Test void finalDiagnosticSaveFailurePreservesRequestedAndDoesNotRepeatRead() {
        var c=diagnosticCandidate("DISPATCHING");String id=UUID.randomUUID().toString();
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(diagnosticLookup(c));
        jdbc.execute("CREATE TRIGGER reject_diagnostic_result BEFORE UPDATE ON manual_order_diagnostics FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='private db failure'");
        try {assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class).hasMessageNotContaining("private db failure");}
        finally {jdbc.execute("DROP TRIGGER reject_diagnostic_result");}
        assertThat(diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단").state()).isEqualTo("REQUESTED");
        verify(diagnosticExecutions,times(1)).findByOrderNumber(c.orderDate(),"0040000638");assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void missing020FailsBeforeLookupButExistingOrderStorageRemainsAvailable() {
        var c=diagnosticCandidate("RESERVED");
        jdbc.execute("RENAME TABLE manual_order_diagnostics TO isolated_diagnostics_hidden");
        try {
            assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),UUID.randomUUID().toString(),"0040000638",true,"잠금 유지 진단")).isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class).hasMessageContaining("020");
            assertThat(commands.verifyStorage()).isNotBlank();
        } finally {jdbc.execute("RENAME TABLE isolated_diagnostics_hidden TO manual_order_diagnostics");}
        verifyNoInteractions(diagnosticExecutions);
    }

    @ParameterizedTest @ValueSource(strings={"STOP_BEFORE_SEND","JOURNAL_FAILURE"})
    void simulationDiagnosisNeverUsesBrokerTruthToUnlockOrResend(String scenario) {
        String id=simSession("1000000");String c=simReady(id,simPlan("BUY","75000","2"),"NEW",null,scenario);
        assertThatThrownBy(()->simulationService.submit(1L,id,c,true,"모의 주문 전송")).isInstanceOf(RuntimeException.class);
        var before=simulationService.get(1L,id);String diagnosticId=UUID.randomUUID().toString();
        var result=simulationService.diagnose(1L,id,c,diagnosticId,"0000000001",true,"잠금 유지 진단");
        assertThat(result.report().assessment()).isEqualTo("STOP_BEFORE_SEND".equals(scenario)?"NOT_FOUND":"FIELDS_MATCH");
        assertThat(simulationService.diagnose(1L,id,c,diagnosticId,"0000000001",true,"잠금 유지 진단")).isEqualTo(result);
        var after=simulationService.get(1L,id);
        assertThat(simCommand(after,c).get("sendCount")).isEqualTo(simCommand(before,c).get("sendCount"));
        assertThat(simCommand(after,c)).containsEntry("status","SENDING");assertThat(after.get("blocked")).isEqualTo(true);
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));assertThat(after.get("positions")).isEqualTo(before.get("positions"));
        assertThat((List<?>)simCommand(after,c).get("diagnostics")).hasSize(1);
        assertThatThrownBy(()->simulationService.diagnose(2L,id,c,UUID.randomUUID().toString(),"0000000001",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
    }

    @Test void failedDiagnosticReservationDoesNotQueryAndRollsBackRequestOnly() {
        var c=diagnosticCandidate("RESERVED");String id=UUID.randomUUID().toString();
        jdbc.execute("CREATE TRIGGER reject_diagnostic_request BEFORE INSERT ON manual_order_diagnostics FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test reservation failure'");
        try {assertThatThrownBy(()->diagnosticService.diagnose(1L,c.commandId(),id,"0040000638",true,"잠금 유지 진단")).isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);}
        finally {jdbc.execute("DROP TRIGGER reject_diagnostic_request");}
        assertThat(diagnosticMapper.find(id,1L)).isNull();verifyNoInteractions(diagnosticExecutions);assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @Test void diagnosticHistoryIsBoundedAndReadOnlyAfterAccountChange() {
        var c=diagnosticCandidate("RESERVED");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(diagnosticLookup(c));
        for(int i=0;i<22;i++) diagnosticService.diagnose(1L,c.commandId(),UUID.randomUUID().toString(),"0040000638",true,"잠금 유지 진단");
        when(binding.matches(FINGERPRINT)).thenReturn(false);
        assertThat(diagnosticService.history(1L,c.commandId())).hasSize(20);
        verify(diagnosticExecutions,times(22)).findByOrderNumber(c.orderDate(),"0040000638");
        assertThat(commands.pending(1L)).isEqualTo(1);
    }

    @ParameterizedTest @ValueSource(strings={"OPEN","PARTIAL","AMEND","CANCEL"})
    void unknownReviewsRequireFreshConfirmationAndPreserveAllOrderGuards(String mode) {
        var c=reviewCandidate(List.of("AMEND","CANCEL").contains(mode)?mode:"NEW");var before=commands.find(c.commandId(),1L);
        var journal=dispatches.find(c.commandId(),1L);
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,mode));
        var prepared=reviewService.prepare(1L,c.commandId(),"0040000639");
        assertThat(prepared.evidence().observation()).isEqualTo("NEW".equals(c.kind())?mode:"CHANGE_REFERENCE");
        assertThat(reviewMapper.preparation(c.commandId(),1L).tokenHash()).isNotEqualTo(prepared.token());
        assertThat(reviewService.history(1L,c.commandId())).isEmpty();
        var result=reviewService.confirm(1L,c.commandId(),prepared.reviewId(),prepared.token(),true,"잠금 유지 대조 저장");
        assertThat(result.lockMaintained()).isTrue();assertThat(reviewMapper.preparation(c.commandId(),1L)).isNull();
        assertThat(commands.find(c.commandId(),1L)).isEqualTo(before);assertThat(dispatches.find(c.commandId(),1L)).isEqualTo(journal);
        assertThat(commands.pending(1L)).isEqualTo(1);assertThat(reviewService.history(1L,c.commandId())).containsExactly(result);
        assertThat(result.toString()).doesNotContain(FINGERPRINT,prepared.token(),"private-name");
        assertThat(reviewService.confirm(1L,c.commandId(),prepared.reviewId(),prepared.token(),true,"잠금 유지 대조 저장")).isEqualTo(result);
        verify(diagnosticExecutions,times(2)).findByOrderNumber(c.orderDate(),"0040000639");
        assertThatThrownBy(()->store.claim(command(approval(),"SENDING"))).isInstanceOf(RuntimeException.class);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_reconciliations",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM trade_records",Integer.class)).isZero();
        if(!"NEW".equals(c.kind())) assertThat(commands.find(c.parentId(),1L).changeId()).isEqualTo(c.commandId());
    }
    @Test void changedFilledQuantityInvalidatesReviewWithoutConsumingToken() {
        var c=reviewCandidate("NEW");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"OPEN"));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"PARTIAL"));
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class).hasMessageContaining("달라졌습니다");
        assertThat(reviewMapper.preparation(c.commandId(),1L)).isNotNull();assertThat(reviewService.history(1L,c.commandId())).isEmpty();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @Test void expiredReplacedWrongTokenForeignUserAndAccountMismatchCannotConfirm() {
        var c=reviewCandidate("NEW");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"OPEN"));
        var old=reviewService.prepare(1L,c.commandId(),"0040000639");var current=reviewService.prepare(1L,c.commandId(),"0040000639");
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),old.reviewId(),old.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->reviewService.confirm(2L,c.commandId(),current.reviewId(),current.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->reviewService.history(2L,c.commandId())).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),current.reviewId(),"wrong",true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        when(binding.matches(FINGERPRINT)).thenReturn(false);
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),current.reviewId(),current.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        when(binding.matches(FINGERPRINT)).thenReturn(true);
        jdbc.update("UPDATE manual_order_review_preparations SET expires_at=? WHERE command_id=?",now().minusSeconds(1),c.commandId());
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),current.reviewId(),current.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        verify(diagnosticExecutions,times(2)).findByOrderNumber(c.orderDate(),"0040000639");assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @Test void concurrentReviewConfirmationStoresOneAuditAndConsumesOnce() throws Exception {
        var c=reviewCandidate("NEW");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"PARTIAL"));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        race(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장"),
            ()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장"));
        assertThat(reviewService.history(1L,c.commandId())).hasSize(1);assertThat(reviewMapper.preparation(c.commandId(),1L)).isNull();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @Test void reviewInsertFailureRollsBackTokenConsumption() {
        var c=reviewCandidate("NEW");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"OPEN"));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        jdbc.execute("CREATE TRIGGER reject_review_insert BEFORE INSERT ON manual_order_reviews FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='private database failure'");
        try{assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class).hasMessageNotContaining("private database failure");}
        finally{jdbc.execute("DROP TRIGGER reject_review_insert");}
        assertThat(reviewMapper.preparation(c.commandId(),1L)).isNotNull();assertThat(reviewService.history(1L,c.commandId())).isEmpty();assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @Test void missing021BlocksOnlyNewReviewBeforeAnyBrokerRead() {
        var c=reviewCandidate("NEW");jdbc.execute("RENAME TABLE manual_order_review_preparations TO isolated_reviews_hidden");
        try{assertThatThrownBy(()->reviewService.prepare(1L,c.commandId(),"0040000639")).isInstanceOf(RuntimeException.class).hasMessageContaining("021");
            assertThat(commands.verifyStorage()).isNotBlank();}
        finally{jdbc.execute("RENAME TABLE isolated_reviews_hidden TO manual_order_review_preparations");}
        verifyNoInteractions(diagnosticExecutions);
    }
    @Test void changingAccountDuringReviewLookupPreventsPreparation() {
        var c=reviewCandidate("NEW");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenAnswer(call->{when(binding.matches(FINGERPRINT)).thenReturn(false);return reviewLookup(c,"OPEN");});
        assertThatThrownBy(()->reviewService.prepare(1L,c.commandId(),"0040000639")).isInstanceOf(RuntimeException.class);
        assertThat(reviewMapper.preparation(c.commandId(),1L)).isNull();assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @ParameterizedTest @ValueSource(strings={"TIMEOUT_AFTER_OPEN","TIMEOUT_AFTER_PARTIAL"})
    void simulationReviewsObserveRemainingQuantityWithoutSendingOrUnlocking(String scenario) {
        String session=simSession("1000000");String id=simReady(session,simPlan("BUY","75000","2"),"NEW",null,scenario);
        var before=simulationService.submit(1L,session,id,true,"모의 주문 전송");
        var p=simulationService.prepareReview(1L,session,id,"0000000001");String review=(String)p.get("reviewId");String token=(String)p.get("token");
        assertThat(before.toString()).doesNotContain("tokenHash","reviewPreparation");
        var after=simulationService.confirmReview(1L,session,id,review,token,true,"잠금 유지 대조 저장");
        simulationService.confirmReview(1L,session,id,review,token,true,"잠금 유지 대조 저장");
        assertThat(simCommand(after,id)).containsEntry("status","UNKNOWN").containsEntry("sendCount",1);
        assertThat((List<?>)simCommand(after,id).get("reviews")).hasSize(1);assertThat(after.get("blocked")).isEqualTo(true);
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));assertThat(after.get("positions")).isEqualTo(before.get("positions"));
        assertThat(after.toString()).doesNotContain(token,"tokenHash","evidenceHash","reviewPreparation");
    }
    @ParameterizedTest @ValueSource(strings={"AMEND","CANCEL"})
    void simulationChangeReviewsKeepParentClaimAndRecordOpaqueEvidence(String kind) {
        String session=simSession("1000000");String parent=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"WAIT");
        simulationService.submit(1L,session,parent,true,"모의 주문 전송");
        String child=simReady(session,simPlan("BUY","74000","2"),kind,parent,"TIMEOUT_AFTER_ACCEPT");
        var before=simulationService.submit(1L,session,child,true,"모의 주문 전송");
        var p=simulationService.prepareReview(1L,session,child,"0000000002");
        var after=simulationService.confirmReview(1L,session,child,(String)p.get("reviewId"),(String)p.get("token"),true,"잠금 유지 대조 저장");
        assertThat(simCommand(after,parent)).isEqualTo(simCommand(before,parent));assertThat(simCommand(after,child)).containsEntry("status","UNKNOWN").containsEntry("sendCount",1);
        assertThat(after.get("availableCash")).isEqualTo(before.get("availableCash"));assertThat(after.get("blocked")).isEqualTo(true);
    }
    @Test void simulationReviewRejectsFillDriftAndExpiredToken() {
        String session=simSession("1000000");String id=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"TIMEOUT_AFTER_OPEN");
        simulationService.submit(1L,session,id,true,"모의 주문 전송");var p=simulationService.prepareReview(1L,session,id,"0000000001");
        simulationService.fill(1L,session,"0000000001",BigDecimal.ONE);
        assertThatThrownBy(()->simulationService.confirmReview(1L,session,id,(String)p.get("reviewId"),(String)p.get("token"),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        var q=simulationService.prepareReview(1L,session,id,"0000000001");
        simulationStore.mutate(1L,session,state->{var c=state.commands.get(id);var r=c.reviewPreparation;c.reviewPreparation=new OrderSimulationState.ReviewPreparation(r.reviewId(),r.tokenHash(),r.evidenceHash(),now().minusSeconds(1).toString(),r.evidence());return null;});
        assertThatThrownBy(()->simulationService.confirmReview(1L,session,id,(String)q.get("reviewId"),(String)q.get("token"),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        assertThat(simulationService.get(1L,session).get("blocked")).isEqualTo(true);
    }
    @Test void preparationExpiringDuringFinalLookupCannotBeConsumedWithEarlierTimestamp() {
        var c=reviewCandidate("NEW");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"OPEN"));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenAnswer(call->{
            jdbc.update("UPDATE manual_order_review_preparations SET expires_at=? WHERE command_id=?",now().minusSeconds(1),c.commandId());return reviewLookup(c,"OPEN");});
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        assertThat(reviewMapper.preparation(c.commandId(),1L)).isNotNull();assertThat(reviewService.history(1L,c.commandId())).isEmpty();
    }

    @Test void changeReviewRechecksParentRowAndPreservesProductionBlock() {
        var c=reviewCandidate("AMEND");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"AMEND"));
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(parentLookup(c,BigDecimal.ZERO));
        var before=commands.find(c.commandId(),1L);var parentBefore=commands.find(c.parentId(),1L);
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");assertThat(p.evidence().parentObservation().verification()).isEqualTo("REFERENCE_MATCH");
        var saved=reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장");
        assertThat(saved.lockMaintained()).isTrue();assertThat(saved.evidence().parentObservation().openQuantity()).isZero();
        assertThat(commands.find(c.commandId(),1L)).isEqualTo(before);assertThat(commands.find(c.parentId(),1L)).isEqualTo(parentBefore);
        assertThat(commands.pending(1L)).isEqualTo(1);
        verify(diagnosticExecutions,times(2)).findByOrderNumber(c.orderDate(),"0040000638");
    }
    @Test void parentOnlyQuantityDriftInvalidatesFinalReview() {
        var c=reviewCandidate("AMEND");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"AMEND"));
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(parentLookup(c,BigDecimal.ZERO));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenReturn(parentLookup(c,BigDecimal.ONE));
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class).hasMessageContaining("달라졌습니다");
        assertThat(reviewMapper.preparation(c.commandId(),1L)).isNotNull();assertThat(reviewService.history(1L,c.commandId())).isEmpty();
        assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @Test void parentLookupFailureIsSanitizedAndSimulationAckCannotConfirmLiveReview() {
        var c=reviewCandidate("CANCEL");when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000639")).thenReturn(reviewLookup(c,"CANCEL"));
        when(diagnosticExecutions.findByOrderNumber(c.orderDate(),"0040000638")).thenThrow(new IllegalStateException("private-key-account"));
        var p=reviewService.prepare(1L,c.commandId(),"0040000639");
        assertThat(p.evidence().parentObservation().verification()).isEqualTo("LOOKUP_FAILED");assertThat(p.toString()).doesNotContain("private-key-account");
        assertThatThrownBy(()->reviewService.confirm(1L,c.commandId(),p.reviewId(),p.token(),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        verify(diagnosticExecutions,times(1)).findByOrderNumber(c.orderDate(),"0040000639");assertThat(commands.pending(1L)).isEqualTo(1);
    }
    @ParameterizedTest @ValueSource(strings={"NEW","AMEND","CANCEL"})
    void virtualCompletionPreservesOriginalAndResourcesThenAllowsNewVirtualOrder(String kind) {
        String session=simSession("1000000");String id=completionCandidate(session,kind);
        var before=simulationService.get(1L,session);var c=simCommand(before,id);String number=(String)c.get("brokerOrderNo");
        var p=simulationService.prepareCompletion(1L,session,id,number);
        assertThat(simulationService.get(1L,session).get("blocked")).isEqualTo(true);
        String resolution=(String)p.get("resolutionId"),token=(String)p.get("token");
        var after=simulationService.confirmCompletion(1L,session,id,resolution,token,true,"가상 주문 종결 확정");
        assertThat(simCommand(after,id)).containsEntry("status","UNKNOWN").containsEntry("resolved",true).containsEntry("sendCount",1);
        assertThat(after.get("blocked")).isEqualTo(false);assertThat(after.get("cash")).isEqualTo(before.get("cash"));
        assertThat(after.get("positions")).isEqualTo(before.get("positions"));assertThat(after.get("availableCash")).isEqualTo(before.get("availableCash"));
        assertThat(after.toString()).doesNotContain(token,"tokenHash","executionKey","completionPreparation");
        simulationService.confirmCompletion(1L,session,id,resolution,token,true,"가상 주문 종결 확정");
        assertThat(((List<?>)simulationService.get(1L,session).get("events")).stream().filter(e->e.toString().contains("가상 종결 확정 ·")).count()).isEqualTo(1);
        String next=simReady(session,simPlan("BUY","75000","1"),"NEW",null,"WAIT");
        assertThat(simCommand(simulationService.submit(1L,session,next,true,"모의 주문 전송"),next)).containsEntry("status","ACCEPTED");
        assertThat(simCommand(simulationService.get(1L,session),id)).containsEntry("sendCount",1);
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM manual_order_commands",Integer.class)).isZero();
        assertThat(jdbc.queryForObject("SELECT COUNT(*) FROM trade_records",Integer.class)).isZero();
    }
    @Test void completingPartialThenFullVirtualFillDoesNotFillAgain() {
        String session=simSession("1000000");String id=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"TIMEOUT_AFTER_PARTIAL");
        simulationService.submit(1L,session,id,true,"모의 주문 전송");
        assertThatThrownBy(()->simulationService.prepareCompletion(1L,session,id,"0000000001")).isInstanceOf(RuntimeException.class);
        var before=simulationService.fill(1L,session,"0000000001",BigDecimal.ONE);var p=simulationService.prepareCompletion(1L,session,id,"0000000001");
        var after=simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정");
        assertThat(after.get("cash")).isEqualTo(before.get("cash"));assertThat(after.get("positions")).isEqualTo(before.get("positions"));
        assertThat(simCommand(after,id)).containsEntry("filledQuantity",new BigDecimal("2")).containsEntry("resolved",true);
    }
    @ParameterizedTest @ValueSource(strings={"TIMEOUT_BEFORE_ACCEPT","STOP_BEFORE_SEND","JOURNAL_FAILURE","SAVE_FAILURE","TIMEOUT_AFTER_OPEN"})
    void unfinishedMissingOrNonterminalVirtualProofCannotResolve(String scenario) {
        String session=simSession("1000000");String id=simReady(session,simPlan("BUY","75000","2"),"NEW",null,scenario);
        try{simulationService.submit(1L,session,id,true,"모의 주문 전송");}catch(RuntimeException expected){}
        assertThatThrownBy(()->simulationService.prepareCompletion(1L,session,id,"0000000001")).isInstanceOf(RuntimeException.class);
        assertThat(simulationService.get(1L,session).get("blocked")).isEqualTo(true);
    }
    @Test void virtualCompletionTokenExpiryReplacementAndOwnerAreEnforced() {
        String session=simSession("1000000");String id=completionCandidate(session,"NEW");
        var first=simulationService.prepareCompletion(1L,session,id,"0000000001");var p=simulationService.prepareCompletion(1L,session,id,"0000000001");
        assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)first.get("resolutionId"),(String)first.get("token"),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->simulationService.confirmCompletion(2L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),false,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"실제 주문 전송")).isInstanceOf(RuntimeException.class);
        simulationStore.mutate(1L,session,state->{var c=state.commands.get(id);var r=c.completionPreparation;c.completionPreparation=new OrderSimulationState.CompletionPreparation(r.resolutionId(),r.tokenHash(),r.evidenceHash(),now().minusSeconds(1).toString(),r.evidence());return null;});
        assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        assertThat(simulationService.get(1L,session).get("blocked")).isEqualTo(true);
    }
    @Test void simultaneousVirtualCompletionAuditsOnceAndKeepsParentClaim() throws Exception {
        String session=simSession("1000000");String id=completionCandidate(session,"CANCEL");var p=simulationService.prepareCompletion(1L,session,id,"0000000002");
        assertThat(race(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정"),
            ()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정"))).containsOnly(true);
        var result=simulationService.get(1L,session);assertThat(result.get("blocked")).isEqualTo(false);
        var state=simulationStore.decode(simulations.find(session,1L).stateJson());assertThat(state.commands.get(state.commands.get(id).parentId).changed).isTrue();
        assertThat(((List<?>)result.get("events")).stream().filter(e->e.toString().contains("가상 종결 확정 ·")).count()).isEqualTo(1);
    }
    @Test void changedVirtualParentAndFailedCommitCannotConsumeCompletion() {
        String session=simSession("1000000");String id=completionCandidate(session,"AMEND");var p=simulationService.prepareCompletion(1L,session,id,"0000000002");
        simulationStore.mutate(1L,session,state->{state.brokerOrders.get("0000000001").filled=BigDecimal.ONE;return null;});
        assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);
        simulationStore.mutate(1L,session,state->{state.brokerOrders.get("0000000001").filled=BigDecimal.ZERO;return null;});
        jdbc.execute("CREATE TRIGGER reject_completion_write BEFORE UPDATE ON order_simulation_sessions FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='test completion failure'");
        try{assertThatThrownBy(()->simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정")).isInstanceOf(RuntimeException.class);}
        finally{jdbc.execute("DROP TRIGGER reject_completion_write");}
        var state=simulationStore.decode(simulations.find(session,1L).stateJson());assertThat(state.commands.get(id).completion).isNull();assertThat(state.commands.get(id).completionPreparation).isNotNull();
        assertThat(simulationService.get(1L,session).get("blocked")).isEqualTo(true);
    }
    @Test void resolvedVirtualCommandDoesNotBypassOtherSendingAndLegacyFieldsStayBlocked() {
        String session=simSession("1000000");String id=completionCandidate(session,"NEW");var p=simulationService.prepareCompletion(1L,session,id,"0000000001");
        String other=simReady(session,simPlan("BUY","75000","1"),"NEW",null,"WAIT");
        simulationStore.mutate(1L,session,state->{state.commands.get(other).status="SENDING";return null;});
        var result=simulationService.confirmCompletion(1L,session,id,(String)p.get("resolutionId"),(String)p.get("token"),true,"가상 주문 종결 확정");
        assertThat(result.get("blocked")).isEqualTo(true);assertThat(simCommand(result,id)).containsEntry("resolved",true);
        String legacy=simSession("1000000");String c=completionCandidate(legacy,"NEW");
        simulationStore.mutate(1L,legacy,state->{state.brokerOrders.get("0000000001").changeKind=null;return null;});
        assertThatThrownBy(()->simulationService.prepareCompletion(1L,legacy,c,"0000000001")).isInstanceOf(RuntimeException.class);
        assertThat(simulationService.get(1L,legacy).get("blocked")).isEqualTo(true);
    }
    private String completionCandidate(String session,String kind){
        if("NEW".equals(kind)){
            String id=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"TIMEOUT_AFTER_ACCEPT");simulationService.submit(1L,session,id,true,"모의 주문 전송");return id;
        }
        String parent=simReady(session,simPlan("BUY","75000","2"),"NEW",null,"WAIT");simulationService.submit(1L,session,parent,true,"모의 주문 전송");
        String child=simReady(session,simPlan("BUY","74000","2"),kind,parent,"TIMEOUT_AFTER_ACCEPT");simulationService.submit(1L,session,child,true,"모의 주문 전송");return child;
    }
    private com.sagopalgo.api.order.dto.KbOrderLookupResponse parentLookup(ManualOrderCommand child,BigDecimal filled){
        var p=commands.find(child.parentId(),1L);var row=new com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse(p.orderNo(),p.stockCode(),"private-name","매수",
            p.createdAt().format(java.time.format.DateTimeFormatter.ofPattern("HHmmss")),p.quantity(),filled,BigDecimal.ZERO,p.price(),null,"","UNKNOWN","","9",p.quantity(),BigDecimal.ZERO);
        return new com.sagopalgo.api.order.dto.KbOrderLookupResponse(p.orderDate(),p.orderNo(),true,1,List.of(row));
    }

    private ManualOrderCommand reviewCandidate(String kind) {
        var t=now();var parent=new ManualOrderCommand(UUID.randomUUID().toString(),1L,approval(),null,"NEW","005930","삼성전자","KOSPI","BUY",
            new BigDecimal("100"),new BigDecimal("2"),FINGERPRINT,null,t.plusSeconds(90),"SENDING",null,t.toLocalDate().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE),null,null,null,t,t);
        store.claim(parent,"parent");dispatchService.begin(parent,"parent");
        dispatchService.recordOutcome(parent,"parent","NEW".equals(kind)?unknown():accepted());dispatchService.complete(1L,parent.commandId());
        if("NEW".equals(kind)) return commands.find(parent.commandId(),1L);
        var child=new ManualOrderCommand(UUID.randomUUID().toString(),1L,null,parent.commandId(),kind,parent.stockCode(),parent.stockName(),parent.market(),parent.side(),
            "AMEND".equals(kind)?new BigDecimal("99"):parent.price(),parent.quantity(),FINGERPRINT,"hash",t.plusSeconds(90),"PREPARED",null,parent.orderDate(),null,null,null,t,t);
        commands.insert(child);store.claim(child,"child");dispatchService.begin(child,"child");dispatchService.recordOutcome(child,"child",unknown());dispatchService.complete(1L,child.commandId());
        return commands.find(child.commandId(),1L);
    }
    private com.sagopalgo.api.order.dto.KbOrderLookupResponse reviewLookup(ManualOrderCommand c,String mode) {
        boolean change=!"NEW".equals(c.kind());BigDecimal filled="PARTIAL".equals(mode)?BigDecimal.ONE:BigDecimal.ZERO;
        BigDecimal open="CANCEL".equals(mode)?BigDecimal.ZERO:c.quantity().subtract(filled);
        var row=new com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse("0040000639",c.stockCode(),"private-name","매수",c.createdAt().format(java.time.format.DateTimeFormatter.ofPattern("HHmmss")),
            c.quantity(),filled,open,c.price(),null,"","PARTIAL".equals(mode)?"PARTIAL":"OPEN",change?"0040000638":"",change?"9":"",change?c.quantity():BigDecimal.ZERO,BigDecimal.ZERO);
        return new com.sagopalgo.api.order.dto.KbOrderLookupResponse(c.orderDate(),"0040000639",true,1,List.of(row));
    }

    private ManualOrderCommand diagnosticCandidate(String phase) {
        var c=command(approval(),"SENDING");
        if("LEGACY_UNVERIFIED".equals(phase)) commands.insert(c);
        else {store.claim(c,"worker");if("DISPATCHING".equals(phase)) dispatchService.begin(c,"worker");}
        return c;
    }
    private com.sagopalgo.api.order.dto.KbOrderLookupResponse diagnosticLookup(ManualOrderCommand c) {
        var row=new com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse("0040000638",c.stockCode(),"private-name","BUY".equals(c.side())?"매수":"매도",
            c.createdAt().format(java.time.format.DateTimeFormatter.ofPattern("HHmmss")),c.quantity(),c.quantity(),BigDecimal.ZERO,c.price(),null,"","FILLED");
        return new com.sagopalgo.api.order.dto.KbOrderLookupResponse(c.orderDate(),"0040000638",true,1,List.of(row));
    }

    private String simSession(String cash) {return (String)simulationService.create(1L,new BigDecimal(cash)).get("sessionId");}
    private OrderPrecheckRequest simPlan(String side,String price,String quantity) {
        return new OrderPrecheckRequest("005930","삼성전자","KOSPI",side,new BigDecimal(price),new BigDecimal(quantity));
    }
    private String simReady(String id,OrderPrecheckRequest plan,String kind,String parent,String scenario) {
        var prepared=simulationService.prepare(1L,id,plan,kind,parent,scenario);
        String command=(String)prepared.get("commandId");
        simulationService.confirm(1L,id,command,(String)prepared.get("token"),true);return command;
    }
    @SuppressWarnings("unchecked")
    private Map<String,Object> simCommand(Map<String,Object> snapshot,String id) {
        return ((List<Map<String,Object>>)snapshot.get("commands")).stream().filter(c->id.equals(c.get("id"))).findFirst().orElseThrow();
    }

    private ManualOrderReconciliationRecord prepareResolution(ManualOrderCommand command, String orderNo) {
        var timestamp = now();
        reconciliations.prepare(new ManualOrderReconciliationPreparation(command.commandId(), 1L, FINGERPRINT,
            orderNo, "h".repeat(64), timestamp.plusSeconds(90), timestamp));
        return new ManualOrderReconciliationRecord(command.commandId(), 1L, FINGERPRINT, command.orderDate(), orderNo,
            "090000", command.quantity(), timestamp);
    }

    private List<Boolean> race(Runnable first, Runnable second) throws Exception {
        var executor = Executors.newFixedThreadPool(2);
        var start = new CountDownLatch(1);
        try {
            var a = executor.submit(() -> runAfter(start, first));
            var b = executor.submit(() -> runAfter(start, second));
            start.countDown();
            return List.of(a.get(20, TimeUnit.SECONDS), b.get(20, TimeUnit.SECONDS));
        } finally { executor.shutdownNow(); }
    }

    private boolean runAfter(CountDownLatch start, Runnable work) throws InterruptedException {
        start.await();
        try { work.run(); return true; } catch (RuntimeException exception) { return false; }
    }

    private long approval() {
        jdbc.update("""
            INSERT INTO order_prechecks (user_id,stock_code,stock_name,market,order_side,requested_price,quantity,
              estimated_amount,quote_provider,current_price) VALUES (1,'005930','삼성전자','KOSPI','BUY',100,1,100,'KB',100)
            """);
        long precheck = jdbc.queryForObject("SELECT MAX(order_precheck_id) FROM order_prechecks", Long.class);
        jdbc.update("""
            INSERT INTO order_approvals (user_id,order_precheck_id,token_hash,status,expires_at,created_at,account_fingerprint)
            VALUES (1,?,?,'ACKNOWLEDGED',?,?,?)
            """, precheck, "t".repeat(64), LocalDateTime.now().plusSeconds(90), LocalDateTime.now(), FINGERPRINT);
        long approval = jdbc.queryForObject("SELECT MAX(order_approval_id) FROM order_approvals", Long.class);
        jdbc.update("""
            INSERT INTO order_submission_guards (order_approval_id,user_id,status,expires_at,created_at,updated_at)
            VALUES (?,1,'READY',?,?,?)
            """, approval, LocalDateTime.now().plusSeconds(90), LocalDateTime.now(), LocalDateTime.now());
        return approval;
    }

    private ManualOrderCommand command(long approval, String status) {
        var timestamp = now();
        return new ManualOrderCommand(UUID.randomUUID().toString(), 1L, approval, null, "NEW", "005930", "삼성전자", "KOSPI", "BUY",
            new BigDecimal("100.00"), new BigDecimal("1.0000"), FINGERPRINT, null, timestamp.plusSeconds(90), status,
            null, timestamp.toLocalDate().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE), null, null, null, timestamp, timestamp);
    }

    private LocalDateTime now() { return LocalDateTime.now(KST).withNano(0); }
}
