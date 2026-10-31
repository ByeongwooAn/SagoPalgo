package com.sagopalgo.api.order.mapper;

import static org.assertj.core.api.Assertions.*;

import com.sagopalgo.api.order.model.ManualOrderCommand;
import com.sagopalgo.api.order.model.ManualOrderReconciliationPreparation;
import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import com.sagopalgo.api.order.service.ManualOrderStore;
import com.sagopalgo.api.order.service.ManualOrderReconciliationStore;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.*;
import org.apache.ibatis.session.Configuration;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
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
    private ManualOrderReconciliationStore reconciliationStore;
    private DataSourceTransactionManager transactions;
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
            jdbc.execute("DROP TABLE IF EXISTS manual_order_reconciliations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_reconciliation_preparations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_observations");
            jdbc.execute("DROP TABLE IF EXISTS manual_order_commands");
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/016_manual_order_commands.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/017_manual_order_reconciliations.sql"));
            // 재적용도 안전한 CREATE IF NOT EXISTS인지 검증합니다.
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/016_manual_order_commands.sql"));
            ScriptUtils.executeSqlScript(connection, new FileSystemResource("../database/migrations/017_manual_order_reconciliations.sql"));
        }
        var configuration = new Configuration();
        configuration.setMapUnderscoreToCamelCase(true);
        configuration.addMapper(ManualOrderMapper.class);
        configuration.addMapper(OrderSubmissionGuardMapper.class);
        configuration.addMapper(ManualOrderReconciliationMapper.class);
        var factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setConfiguration(configuration);
        var session = new SqlSessionTemplate(factory.getObject());
        commands = session.getMapper(ManualOrderMapper.class);
        reconciliations = session.getMapper(ManualOrderReconciliationMapper.class);
        transactions = new DataSourceTransactionManager(dataSource);
        store = proxy(new ManualOrderStore(commands, session.getMapper(OrderSubmissionGuardMapper.class)));
        reconciliationStore = proxy(new ManualOrderReconciliationStore(commands, reconciliations));
    }

    @SuppressWarnings("unchecked")
    private <T> T proxy(T target) {
        var factory = new ProxyFactory(target);
        factory.setProxyTargetClass(true);
        factory.addAdvice(new TransactionInterceptor(transactions, new AnnotationTransactionAttributeSource()));
        return (T) factory.getProxy();
    }

    @BeforeEach void resetOnlyIsolatedOrderTables() {
        for (String table : List.of("manual_order_reconciliations", "manual_order_reconciliation_preparations",
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
            null, "20261031", null, null, null, timestamp, timestamp);
    }

    private LocalDateTime now() { return LocalDateTime.now(KST).withNano(0); }
}
