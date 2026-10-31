package com.sagopalgo.api.order.simulation;
import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.service.OrderDispatchReceipt;
import com.sagopalgo.api.order.simulation.OrderSimulationState.*;
import java.math.BigDecimal;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.junit.jupiter.api.Test;
class SimulationCompletionRulesTest {
    @ParameterizedTest @ValueSource(strings={"NEW","AMEND","CANCEL"}) void requiresExplicitVirtualTerminalProof(String kind) {
        var state=state(kind);var c=state.commands.get("child");var proof=SimulationCompletionRules.inspect(state,c,"0000000002");
        assertThat(proof.source()).isEqualTo("SIMULATION");
        c.completion=new StoredCompletion("resolution","a".repeat(64),proof,"2026-11-01T09:00:01");assertThat(SimulationCompletionRules.resolved(c)).isTrue();
    }
    @ParameterizedTest @ValueSource(strings={"sending","phase","receipt","execution","sendCount","owner","kind","open","partial","changedNew",
        "parentClaim","parentState","parentOwner","original","parentFilled","parentOpen","price"})
    void incompleteOrForeignProofNeverResolvesUnknown(String type) {
        boolean parent=java.util.Set.of("parentClaim","parentState","parentOwner","original","parentFilled","parentOpen","price").contains(type);
        var state=state(parent?"AMEND":"NEW");var c=state.commands.get("child");var b=state.brokerOrders.get("0000000002");
        switch(type){
            case "sending"->c.status="SENDING";case "phase"->c.dispatchPhase=null;case "receipt"->c.receipt=new OrderDispatchReceipt("ACCEPTED","0000000002","200","A");
            case "execution"->c.executionKey=null;case "sendCount"->c.sendCount=2;case "owner"->b.commandId="other";case "kind"->b.changeKind="CANCEL";
            case "open"->{b.status="OPEN";b.filled=BigDecimal.ZERO;}case "partial"->{b.status="PARTIAL";b.filled=BigDecimal.ONE;}case "changedNew"->c.changed=true;
            case "parentClaim"->state.commands.get("parent").changed=false;case "parentState"->state.commands.get("parent").status="UNKNOWN";
            case "parentOwner"->state.brokerOrders.get("0000000001").changedByCommandId="other";case "original"->b.originalOrderNo="0000000010";
            case "parentFilled"->state.brokerOrders.get("0000000001").filled=BigDecimal.ONE;
            case "parentOpen"->state.brokerOrders.get("0000000001").status="OPEN";
            case "price"->{c.plan=plan("100");b.plan=c.plan;}default->throw new AssertionError(type);
        }
        assertThatThrownBy(()->SimulationCompletionRules.inspect(state,c,"0000000002")).isInstanceOf(RuntimeException.class);
        assertThat(SimulationCompletionRules.resolved(c)).isFalse();
    }
    @Test void nonSimulationSourceAndLegacyOrMalformedAuditCannotSuppressBlock() {
        var s=state("NEW");var c=s.commands.get("child");var e=SimulationCompletionRules.inspect(s,c,"0000000002");
        var forged=new SimulationCompletionRules.Evidence("KB",e.commandId(),e.kind(),e.outcome(),e.orderNo(),e.parentOrderNo(),e.stockCode(),e.market(),e.side(),
            e.price(),e.quantity(),e.filledQuantity(),e.openQuantity(),e.parentState(),e.parentFilled(),e.parentOpen());
        c.completion=new StoredCompletion("id","a".repeat(64),forged,"2026-11-01T09:00:01");assertThat(SimulationCompletionRules.resolved(c)).isFalse();
        c.completion=new StoredCompletion("id","a".repeat(64),e,"invalid-time");assertThat(SimulationCompletionRules.resolved(c)).isFalse();
        c.completion=new StoredCompletion("id","a".repeat(64),e,"2026-11-01T09:00:01");c.dispatchPhase=null;assertThat(SimulationCompletionRules.resolved(c)).isFalse();
    }
    private OrderSimulationState state(String kind) {
        var s=new OrderSimulationState();var c=new Command();c.id="child";c.kind=kind;c.plan=plan("AMEND".equals(kind)?"99":"100");
        c.status="UNKNOWN";c.dispatchPhase="RETURNED";c.receipt=new OrderDispatchReceipt("UNKNOWN","","","");c.sendCount=1;c.executionKey="owner";c.brokerOrderNo="0000000002";
        s.commands.put(c.id,c);var b=new BrokerOrder();b.commandId=c.id;b.orderNo=c.brokerOrderNo;b.changeKind=kind;b.plan=c.plan;
        b.status="CANCEL".equals(kind)?"CANCELLED":"FILLED";b.filled="CANCEL".equals(kind)?BigDecimal.ZERO:new BigDecimal("2");s.brokerOrders.put(b.orderNo,b);
        if(!"NEW".equals(kind)){
            var p=new Command();p.id="parent";p.kind="NEW";p.plan=plan("100");p.status="ACCEPTED";p.changed=true;p.brokerOrderNo="0000000001";s.commands.put(p.id,p);c.parentId=p.id;
            var pb=new BrokerOrder();pb.commandId=p.id;pb.orderNo=p.brokerOrderNo;pb.plan=p.plan;pb.changeKind="NEW";pb.changedByCommandId=c.id;pb.status="AMEND".equals(kind)?"REPLACED":"CANCELLED";
            s.brokerOrders.put(pb.orderNo,pb);b.originalOrderNo=pb.orderNo;
        }
        return s;
    }
    private OrderPrecheckRequest plan(String price){return new OrderPrecheckRequest("005930","삼성전자","KOSPI","BUY",new BigDecimal(price),new BigDecimal("2"));}
}
