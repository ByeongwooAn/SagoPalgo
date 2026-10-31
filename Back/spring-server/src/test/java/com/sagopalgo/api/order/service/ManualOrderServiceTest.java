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
    ManualOrderDispatchService dispatch=mock(ManualOrderDispatchService.class);
    ManualOrderService service=new ManualOrderService(mapper,prechecks,precheck,binding,readiness,executions,client,store,dispatch);
    @BeforeEach void setup() {
        when(readiness.status()).thenReturn(new OrderReadinessResponse(true,List.of()));
        when(binding.requireFingerprint()).thenReturn("fingerprint");when(binding.matches("fingerprint")).thenReturn(true);
        OrderPrecheckRecord p=new OrderPrecheckRecord();p.setStockCode("005930");p.setStockName("삼성전자");
        p.setMarket("KOSPI");p.setOrderSide("BUY");p.setRequestedPrice(new BigDecimal("100"));p.setQuantity(BigDecimal.ONE);
        when(prechecks.findForApproval(7L,1L)).thenReturn(p);
        OrderPrecheckResponse check=mock(OrderPrecheckResponse.class);
        when(check.eligible()).thenReturn(true);when(check.checks()).thenReturn(List.of());when(precheck.precheck(eq(1L),any())).thenReturn(check);
        when(mapper.finish(anyString(),eq(1L),anyString(),anyString(),anyString(),anyString(),any())).thenReturn(1);
        doAnswer(invocation -> {ManualOrderCommand c=invocation.getArgument(0);when(mapper.find(c.commandId(),1L)).thenReturn(c);return null;}).when(store).claim(any(),anyString());
    }
    @Test void commitsClaimBeforeSingleBrokerCallAndNeverExposesRawMessage() {
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","OK","private-account"));
        service.submit(1L,7L,true,"실제 주문 전송");
        var order=inOrder(store,client,dispatch);order.verify(store).claim(any(),anyString());order.verify(dispatch).begin(any(),anyString());order.verify(client).sendOrderOnce(any());
        order.verify(dispatch).recordOutcome(any(),anyString(),argThat(o->o.status()==KbLimitOrderContract.Status.ACCEPTED));
        order.verify(dispatch).complete(eq(1L),anyString());
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
        doThrow(new ApiException(ErrorCode.DUPLICATE_RESOURCE)).when(store).claim(any(),anyString());
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client);
    }
    @Test void timeoutPersistsUnknownAndDoesNotRetry() {
        when(client.sendOrderOnce(any())).thenThrow(new IllegalStateException("secret-timeout"));
        service.submit(1L,7L,true,"실제 주문 전송");
        verify(dispatch).recordOutcome(any(),anyString(),argThat(o->o.status()==KbLimitOrderContract.Status.UNKNOWN));
        verify(client,times(1)).sendOrderOnce(any());
    }
    @Test void failedDispatchStartNeverCallsBrokerAndPersistsConservativeUnknown() {
        doThrow(new IllegalStateException("start commit failed")).when(dispatch).begin(any(),anyString());
        service.submit(1L,7L,true,"실제 주문 전송");
        verifyNoInteractions(client);
        verify(dispatch).recordOutcome(any(),anyString(),argThat(o->o.status()==KbLimitOrderContract.Status.UNKNOWN));
    }
    @Test void receiptCommitFailureLeavesCommandUnappliedAndNeverResends() {
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","A",""));
        doThrow(new IllegalStateException("journal commit failed")).when(dispatch).recordOutcome(any(),anyString(),any());
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(IllegalStateException.class);
        verify(dispatch,never()).complete(any(),any());
        verify(client,times(1)).sendOrderOnce(any());
        verify(store,times(1)).claim(any(),anyString());
    }
    @Test void resultPersistenceFailureDoesNotResendOrReleaseClaim() {
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000638","200","",""));
        doThrow(new ApiException(ErrorCode.INTERNAL_ERROR)).when(dispatch).complete(eq(1L),anyString());
        assertThatThrownBy(()->service.submit(1L,7L,true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verify(client,times(1)).sendOrderOnce(any());verify(store,times(1)).claim(any(),anyString());
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
    @Test void partialFillAndUnverifiedCashPreventChange() {
        ManualOrderCommand parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        var partial=new KbOrderExecutionItemResponse(parent.orderNo(),"005930","삼성전자","매수","090000",BigDecimal.ONE,
            new BigDecimal("0.5"),new BigDecimal("0.5"),new BigDecimal("100"),new BigDecimal("100"),"","PARTIAL");
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,partial));
        assertThatThrownBy(()->service.prepareChange(1L,"parent","CANCEL",null)).isInstanceOf(ApiException.class);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);
    }
    @Test void increasedBuyPriceRequiresFullFreshCashAtPrepareAndSubmit() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        var check=amendCheck("101",true);when(precheck.precheck(eq(1L),any())).thenReturn(check);
        var prepared=service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"));
        var child=captureChild();when(mapper.find(child.commandId(),1L)).thenReturn(child);
        when(client.sendOrderOnce(any())).thenReturn(new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.ACCEPTED,"0040000639","200","A",""));
        service.submitChange(1L,child.commandId(),prepared.token(),true,"실제 주문 전송");
        verify(precheck,times(2)).precheck(eq(1L),argThat(p->p.limitPrice().compareTo(new BigDecimal("101"))==0 && p.quantity().compareTo(BigDecimal.ONE)==0));
        verify(client).sendOrderOnce(argThat(r->r.path().equals("/api/v1/ssam1805")
            && "101".equals(r.dataBody().get("ordr_uprc")) && "2".equals(r.dataBody().get("crct_clsf"))));
        verify(store,times(1)).claim(any(),anyString());
    }
    @Test void increasedBuyCannotUseDeltaOrMissingCashCheckEvenIfOtherChecksPass() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        for(var cash:java.util.Arrays.asList(null,"1","100")) {
            doReturn(amendCheck(cash,true)).when(precheck).precheck(eq(1L),any());
            assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        }
        var missing=amendCheck("1000",true);when(missing.checks()).thenReturn(List.of());when(precheck.precheck(eq(1L),any())).thenReturn(missing);
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        doReturn(amendCheck("1000",false)).when(precheck).precheck(eq(1L),any());
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        verify(mapper,never()).insert(any());verifyNoInteractions(client,store);
    }
    @Test void cashLostAfterPrepareBlocksBeforeClaimWithoutConsumingParent() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        doReturn(amendCheck("101",true),amendCheck("1",false)).when(precheck).precheck(eq(1L),any());
        var prepared=service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"));var child=captureChild();
        when(mapper.find(child.commandId(),1L)).thenReturn(child);
        assertThatThrownBy(()->service.submitChange(1L,child.commandId(),prepared.token(),true,"실제 주문 전송")).isInstanceOf(ApiException.class);
        verifyNoInteractions(client,store);verify(mapper,never()).claimParent(any(),any(),any(),any());
    }
    @Test void unchangedPriceAndFailedMarketChecksCannotPrepareAmendment() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("100.00"))).isInstanceOf(ApiException.class);
        var check=amendCheck("1000",true);when(check.checks()).thenReturn(List.of(new OrderSafetyCheckResponse("REAL_PRICE","현재가",false,"실패")));
        when(precheck.precheck(eq(1L),any())).thenReturn(check);
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        verify(mapper,never()).insert(any());verifyNoInteractions(client,store);
    }
    @Test void lowerBuyPriceDoesNotRequireFreshCashOnTopOfExistingReservation() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        doReturn(amendCheck("0",false)).when(precheck).precheck(eq(1L),any());
        assertThat(service.prepareChange(1L,"parent","AMEND",new BigDecimal("99")).command().price()).isEqualByComparingTo("99");
        verifyNoInteractions(client,store);
    }
    @Test void changedBindingDuringPrecheckPreventsPreparation() {
        var parent=command("NEW","ACCEPTED");when(mapper.find("parent",1L)).thenReturn(parent);
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row()));
        when(precheck.precheck(eq(1L),any())).thenAnswer(i->{when(binding.matches("fingerprint")).thenReturn(false);return amendCheck("1000",true);});
        assertThatThrownBy(()->service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"))).isInstanceOf(ApiException.class);
        verify(mapper,never()).insert(any());verifyNoInteractions(client,store);
    }
    @Test void increasedSellPriceKeepsReservedSharesAndDoesNotRequireBuyCash() {
        var parent=command("NEW","ACCEPTED","SELL");when(mapper.find("parent",1L)).thenReturn(parent);
        var row=new KbOrderExecutionItemResponse(parent.orderNo(),"005930","삼성전자","매도","090000",BigDecimal.ONE,
            BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("100"),null,"","OPEN");
        when(executions.findByOrderNumber(parent.orderDate(),parent.orderNo())).thenReturn(lookup(true,row));
        var check=amendCheck("0",false);when(check.checks()).thenReturn(List.of(new OrderSafetyCheckResponse("REAL_PRICE","현재가",true,"확인"),
            new OrderSafetyCheckResponse("SELLABLE_QUANTITY","수량",false,"원주문 예약")));when(precheck.precheck(eq(1L),any())).thenReturn(check);
        var prepared=service.prepareChange(1L,"parent","AMEND",new BigDecimal("101"));
        assertThat(prepared.command().quantity()).isEqualByComparingTo("1");assertThat(prepared.command().price()).isEqualByComparingTo("101");
        verifyNoInteractions(client,store);
    }
    private OrderPrecheckResponse amendCheck(String cash,boolean buyingPower) {
        var check=mock(OrderPrecheckResponse.class);when(check.orderAvailableCash()).thenReturn(cash==null?null:new BigDecimal(cash));
        when(check.checks()).thenReturn(List.of(new OrderSafetyCheckResponse("REAL_PRICE","현재가",true,"확인"),
            new OrderSafetyCheckResponse("BUYING_POWER","주문가능현금",buyingPower,"자원")));
        return check;
    }
    private ManualOrderCommand captureChild() {
        var child=ArgumentCaptor.forClass(ManualOrderCommand.class);verify(mapper).insert(child.capture());return child.getValue();
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
        return command(kind,status,"BUY");
    }
    private ManualOrderCommand command(String kind,String status,String side) {
        LocalDateTime now=LocalDateTime.now(ZoneId.of("Asia/Seoul"));
        return new ManualOrderCommand("parent",1L,7L,null,kind,"005930","삼성전자","KOSPI",side,new BigDecimal("100"),
            BigDecimal.ONE,"fingerprint",null,now.plusSeconds(90),status,"0040000638",LocalDate.now(ZoneId.of("Asia/Seoul")).format(DateTimeFormatter.BASIC_ISO_DATE),"200","",null,now,now);
    }
    private KbOrderExecutionItemResponse row(){return new KbOrderExecutionItemResponse("0040000638","005930","삼성전자","매수","090000",BigDecimal.ONE,
        BigDecimal.ZERO,BigDecimal.ONE,new BigDecimal("100"),null,"","OPEN");}
    private KbOrderLookupResponse lookup(boolean complete,KbOrderExecutionItemResponse... rows){return new KbOrderLookupResponse("20261031","0040000638",complete,1,List.of(rows));}
}
