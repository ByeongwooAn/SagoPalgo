package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;
import static org.mockito.ArgumentMatchers.*;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.dto.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import java.math.BigDecimal;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.List;
import org.junit.jupiter.api.*;
import org.mockito.ArgumentCaptor;
import org.springframework.dao.DataAccessResourceFailureException;

class ManualOrderServiceTest {
    ManualOrderMapper mapper=mock(ManualOrderMapper.class);
    OrderPrecheckMapper prechecks=mock(OrderPrecheckMapper.class);
    OrderPrecheckService precheck=mock(OrderPrecheckService.class);
    OrderAccountBinding binding=mock(OrderAccountBinding.class);
    OrderReadinessService readiness=mock(OrderReadinessService.class);
    KbOrderExecutionService executions=mock(KbOrderExecutionService.class);
    KbSecuritiesAccountClient client=mock(KbSecuritiesAccountClient.class);
    ManualOrderStore store=mock(ManualOrderStore.class);
    ManualOrderService service=new ManualOrderService(mapper,prechecks,precheck,binding,readiness,executions,client,store);
    @BeforeEach void setup() {
        when(readiness.status()).thenReturn(new OrderReadinessResponse(true,List.of()));
        when(binding.requireFingerprint()).thenReturn("fingerprint");when(binding.matches("fingerprint")).thenReturn(true);
        OrderPrecheckRecord p=new OrderPrecheckRecord();p.setStockCode("005930");p.setStockName("삼성전자");
        p.setMarket("KOSPI");p.setOrderSide("BUY");p.setRequestedPrice(new BigDecimal("100"));p.setQuantity(BigDecimal.ONE);
        when(prechecks.findForApproval(7L,1L)).thenReturn(p);
        OrderPrecheckResponse check=mock(OrderPrecheckResponse.class);
        when(check.eligible()).thenReturn(true);when(check.checks()).thenReturn(List.of());when(precheck.precheck(eq(1L),any())).thenReturn(check);
        when(mapper.finish(anyString(),eq(1L),anyString(),anyString(),anyString(),anyString(),any())).thenReturn(1);
        doAnswer(invocation -> {ManualOrderCommand c=invocation.getArgument(0);when(mapper.find(c.commandId(),1L)).thenReturn(c);return null;}).when(store).claim(any());
    }
    @Test void commitsClaimBeforeSingleBrokerCallAndNeverExposesRawMessage() {
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","OK","private-account"));
        service.submit(1L,7L,true,"실제 주문 전송");
        var order=inOrder(store,client,mapper);order.verify(store).claim(any());order.verify(client).sendOrderOnce(any());
        order.verify(mapper).finish(anyString(),eq(1L),eq("ACCEPTED"),eq("0040000638"),eq("200"),eq("OK"),any());
        verify(client,times(1)).sendOrderOnce(any());
        assertThat(service.history(1L)).isEmpty();
    }
    @Test void requiresSeparateActualOrderAcknowledgement() {
        assertThatThrownBy(()->service.submit(1L,7L,false,"실제 주문 전송")).isInstanceOf(ApiException.class);
        assertThatThrownBy(()->service.submit(1L,7L,true,"승인")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store,precheck);
    }
    @Test void repeatedApprovalReturnsRecordedResultWithoutNetwork() {
        when(mapper.findApproval(7L,1L)).thenReturn(command("NEW","UNKNOWN"));
        assertThat(service.submit(1L,7L,true,"실제 주문 전송").status()).isEqualTo("UNKNOWN");
        verifyNoInteractions(client,store,precheck,executions);
    }
    @Test void disabledReadinessBlocksAllBrokerCalls() {
        when(readiness.status()).thenReturn(new OrderReadinessResponse(false,List.of()));
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store,precheck,executions);
    }
    @Test void missingMigrationFailsBeforeExternalReads() {
        when(mapper.verifyStorage()).thenThrow(new DataAccessResourceFailureException("private-db"));
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송"))
            .isInstanceOf(ApiException.class).hasMessageNotContaining("private-db");
        verifyNoInteractions(client,store,precheck,executions);
    }
    @Test void otherUsersApprovalIsUnavailable() {
        when(prechecks.findForApproval(7L,1L)).thenReturn(null);
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void failedFreshCheckDoesNotConsumeOrSubmit() {
        OrderPrecheckResponse blocked=mock(OrderPrecheckResponse.class);
        when(blocked.eligible()).thenReturn(false);
        when(precheck.precheck(eq(1L),any())).thenReturn(blocked);
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void readOnlyPermissionFailurePreventsClaim() {
        when(executions.page(anyString(),eq("0"),eq(""))).thenThrow(new ApiException(ErrorCode.EXTERNAL_DATA_ERROR));
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void failedDurableClaimNeverCallsTransport() {
        doThrow(new ApiException(ErrorCode.DUPLICATE_RESOURCE)).when(store).claim(any());
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client);
    }
    @Test void timeoutPersistsUnknownAndDoesNotRetry() {
        when(client.sendOrderOnce(any())).thenThrow(new IllegalStateException("secret-timeout"));
        service.submit(1L,7L,true,"실제 주문 전송");
        verify(mapper).finish(anyString(),eq(1L),eq("UNKNOWN"),eq(""),eq(""),eq(""),any());
        verify(client,times(1)).sendOrderOnce(any());
    }
    @Test void resultPersistenceFailureDoesNotResendOrReleaseClaim() {
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","",""));
        when(mapper.finish(anyString(),eq(1L),anyString(),anyString(),anyString(),anyString(),any())).thenReturn(0);
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verify(client,times(1)).sendOrderOnce(any());verify(store,times(1)).claim(any());
    }
    @Test void syncNeedsCompleteUniqueExactMatchAndKeepsOriginalSubmission() {
        ManualOrderCommand c=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(c);
        when(executions.findByOrderNumber(c.orderDate(),c.orderNo())).thenReturn(lookup(false,row()));
        assertThat(service.sync(1L,"parent").status()).isEqualTo("UNKNOWN");
        when(executions.findByOrderNumber(c.orderDate(),c.orderNo())).thenReturn(lookup(true,row(),row()));
        assertThat(service.sync(1L,"parent").status()).isEqualTo("UNKNOWN");
        when(executions.findByOrderNumber(c.orderDate(),c.orderNo())).thenReturn(lookup(true,row()));
        assertThat(service.sync(1L,"parent").status()).isEqualTo("OPEN");
        verify(mapper,never()).finish(any(),any(),any(),any(),any(),any(),any());
    }
    @Test void changedAccountBlocksSyncAndChanges() {
        when(mapper.find("parent",1L)).thenReturn(command("NEW","ACCEPTED"));when(binding.matches(any())).thenReturn(false);
        assertThatThrownBy(()->service.sync(1L,"parent")).isInstanceOf(ApiException.class);
        verifyNoInteractions(executions,client);
    }
    @Test void cancelPreparationAndSubmitUseOriginalBrokerNumberAndConsumeOnce() {
        ManualOrderCommand parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        var preparation=service.prepareChange(1L,"parent","CANCEL",null);
        ArgumentCaptor<ManualOrderCommand> captor=ArgumentCaptor.forClass(ManualOrderCommand.class);verify(mapper).insert(captor.capture());
        ManualOrderCommand child=captor.getValue();when(mapper.find(child.commandId(),1L)).thenReturn(child);
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000639","200","",""));
        service.submitChange(1L,child.commandId(),preparation.token(),true,"실제 주문 전송");
        ArgumentCaptor<KbLimitOrderContract.Request> request=ArgumentCaptor.forClass(KbLimitOrderContract.Request.class);
        verify(client).sendOrderOnce(request.capture());assertThat(request.getValue().path()).isEqualTo("/api/v1/ssam1806");
        assertThat(request.getValue().dataBody()).containsEntry("orgn_ordr_no","0040000638").containsEntry("crct_clsf","2");
        assertThat(preparation.command().toString()).doesNotContain(child.tokenHash(),"fingerprint");
    }
    @Test void partialFillPreventsChangeAndPriceIncreaseIsRejected() {
        ManualOrderCommand parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        var partial=new KbOrderExecutionItemResponse(parent.orderNo(),"005930","삼성전자","매수","090000",BigDecimal.ONE,
            new BigDecimal("0.5"),new BigDecimal("0.5"),new BigDecimal("100"),new BigDecimal("100"),"","PARTIAL");
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,partial));
        assertThatThrownBy(()->service.prepareChange(1L,"parent","CANCEL",null)).isInstanceOf(ApiException.class);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void changedOrderAfterPreparationPreventsTransmission() {
        ManualOrderCommand parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        var preparation=service.prepareChange(1L,"parent","CANCEL",null);
        ArgumentCaptor<ManualOrderCommand> captor=ArgumentCaptor.forClass(ManualOrderCommand.class);verify(mapper).insert(captor.capture());
        ManualOrderCommand child=captor.getValue();when(mapper.find(child.commandId(),1L)).thenReturn(child);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true));
        assertThatThrownBy(()->service.submitChange(1L,child.commandId(),preparation.token(),true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void amendmentUsesApprovedLowerPriceAndOfficialAllChangeFields() {
        ManualOrderCommand parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        var preparation=service.prepareChange(1L,"parent","AMEND",new BigDecimal("99"));
        ArgumentCaptor<ManualOrderCommand> captor=ArgumentCaptor.forClass(ManualOrderCommand.class);verify(mapper).insert(captor.capture());
        ManualOrderCommand child=captor.getValue();when(mapper.find(child.commandId(),1L)).thenReturn(child);
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000639","200","",""));
        service.submitChange(1L,child.commandId(),preparation.token(),true,"실제 주문 전송");
        ArgumentCaptor<KbLimitOrderContract.Request> request=ArgumentCaptor.forClass(KbLimitOrderContract.Request.class);
        verify(client).sendOrderOnce(request.capture());assertThat(request.getValue().path()).isEqualTo("/api/v1/ssam1805");
        assertThat(request.getValue().dataBody()).containsEntry("ordr_uprc","99").containsEntry("crct_clsf","2")
            .containsEntry("mkt_tm_clsf","1").containsEntry("ordr_ccd","00").containsEntry("sor_ordr_ccd","K");
    }

    private ManualOrderCommand command(String kind,String status) {
        LocalDateTime now=LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        return new ManualOrderCommand("parent",1L,7L,null,kind,"005930","삼성전자","KOSPI","BUY",new BigDecimal("100"),
            BigDecimal.ONE,"fingerprint",null,now.plusSeconds(90),status,"0040000638",LocalDate.now(ZoneId.of("Asia/Seoul")).format(DateTimeFormatter.BASIC_ISO_DATE),"200","",null,now,now);
    }
    private KbOrderExecutionItemResponse row(){return new KbOrderExecutionItemResponse("0040000638","005930","삼성전자","매수","090000",BigDecimal.ONE,
        BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("100"),null,"","OPEN");}
    private KbOrderLookupResponse lookup(boolean complete,KbOrderExecutionItemResponse... rows){return new KbOrderLookupResponse("20261031","0040000638",complete,1,List.of(rows));}
}
