package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.ManualOrderCommand;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.junit.jupiter.api.*;
import org.springframework.aop.framework.ProxyFactory;
import org.springframework.transaction.*;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionInterceptor;
import org.springframework.transaction.support.SimpleTransactionStatus;

class ManualOrderStoreTest {
    ManualOrderMapper mapper=mock(ManualOrderMapper.class);
    OrderSubmissionGuardMapper guards=mock(OrderSubmissionGuardMapper.class);
    ManualOrderDispatchMapper dispatch=mock(ManualOrderDispatchMapper.class);
    PlatformTransactionManager tx=mock(PlatformTransactionManager.class);
    ManualOrderStore store;
    @BeforeEach void setup() {
        when(tx.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        when(mapper.lockUser(1L)).thenReturn(1L);
        when(guards.reserveOnce(eq(7L),eq(1L),eq("fingerprint"),any())).thenReturn(1);
        when(dispatch.reserve(any(),any(),any(),any())).thenReturn(1);
        ProxyFactory factory=new ProxyFactory(new ManualOrderStore(mapper,guards,dispatch));
        factory.setProxyTargetClass(true);
        factory.addAdvice(new TransactionInterceptor(tx,new AnnotationTransactionAttributeSource()));
        store=(ManualOrderStore)factory.getProxy();
    }
    @Test void guardAndAuditCommitBeforeReturningToCaller() {
        store.claim(command("NEW"));
        var order=inOrder(tx,mapper,guards,dispatch);
        order.verify(tx).getTransaction(argThat(d->d.getPropagationBehavior()==TransactionDefinition.PROPAGATION_REQUIRES_NEW));
        order.verify(mapper).lockUser(1L);order.verify(mapper).pending(1L);
        order.verify(guards).reserveOnce(eq(7L),eq(1L),eq("fingerprint"),any());
        order.verify(mapper).insert(any());order.verify(dispatch).reserve(any(),any(),any(),any());order.verify(tx).commit(any());
    }
    @Test void failedInsertRollsBackGuardAndThrowsBeforeHttpCouldStart() {
        when(mapper.insert(any())).thenThrow(new IllegalStateException("database"));
        assertThatThrownBy(()->store.claim(command("NEW"))).isInstanceOf(IllegalStateException.class);
        verify(tx).rollback(any());verify(tx,never()).commit(any());
    }
    @Test void unresolvedTransmissionBlocksDifferentApproval() {
        when(mapper.pending(1L)).thenReturn(1);
        assertThatThrownBy(()->store.claim(command("NEW"))).isInstanceOf(ApiException.class);
        verifyNoInteractions(guards);verify(mapper,never()).insert(any());
    }
    @Test void consumedOrExpiredApprovalCannotInsert() {
        when(guards.reserveOnce(any(),any(),any(),any())).thenReturn(0);
        assertThatThrownBy(()->store.claim(command("NEW"))).isInstanceOf(ApiException.class);
        verify(mapper,never()).insert(any());verify(tx).rollback(any());
    }
    @Test void expiredChangeRollsBackParentClaim() {
        when(mapper.claimParent(eq("parent"),eq("child"),eq(1L),any())).thenReturn(1);
        when(mapper.claimChange(any(),any(),any(),any(),any())).thenReturn(0);
        assertThatThrownBy(()->store.claim(command("CANCEL"))).isInstanceOf(ApiException.class);
        verify(tx).rollback(any());verify(tx,never()).commit(any());
    }
    private ManualOrderCommand command(String kind) {
        LocalDateTime now=LocalDateTime.now();
        return new ManualOrderCommand("child",1L,"NEW".equals(kind)?7L:null,"NEW".equals(kind)?null:"parent",kind,
            "005930","삼성전자","KOSPI","BUY",BigDecimal.TEN,BigDecimal.ONE,"fingerprint","hash",now.plusSeconds(90),
            "NEW".equals(kind)?"SENDING":"PREPARED",null,"20261031",null,null,null,now,now);
    }
}
