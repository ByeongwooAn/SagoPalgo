package com.sagopalgo.api.order.simulation;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.service.*;
import com.sagopalgo.api.order.simulation.OrderSimulationState.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;

/** 가상 증권사의 소유권·명시적 종결 상태만 판정합니다. KB 응답이나 실계좌에는 적용하지 않습니다. */
public final class SimulationCompletionRules {
    private SimulationCompletionRules(){}
    public static final String CONFIRMATION="가상 주문 종결 확정";
    public static Evidence inspect(OrderSimulationState state,Command c,String number) {
        UnknownOrderReviewRules.number(number);
        if(!"UNKNOWN".equals(c.status) || !"RETURNED".equals(c.dispatchPhase) || c.receipt==null || !c.receipt.valid()
            || !"UNKNOWN".equals(c.receipt.status()) || c.sendCount!=1 || c.executionKey==null || c.executionKey.isBlank()) throw invalid();
        var child=state.brokerOrders.get(number);
        if(child==null || !number.equals(c.brokerOrderNo) || !number.equals(child.orderNo) || !c.id.equals(child.commandId)
            || !c.kind.equals(child.changeKind) || !plan(c.plan,child.plan)) throw invalid();
        String outcome,parentNo="",parentState="";BigDecimal parentFilled=null,parentOpen=null;
        if("NEW".equals(c.kind)) {
            if(c.parentId!=null || c.changed || !filled(child)) throw invalid();
            outcome="FILLED";
        } else {
            var parent=state.commands.get(c.parentId);
            if(parent==null || !"NEW".equals(parent.kind) || !"ACCEPTED".equals(parent.status) || !parent.changed) throw invalid();
            var original=state.brokerOrders.get(parent.brokerOrderNo);
            if(original==null || !parent.id.equals(original.commandId) || !"NEW".equals(original.changeKind)
                || !plan(parent.plan,original.plan) || !c.id.equals(original.changedByCommandId)
                || !parent.brokerOrderNo.equals(child.originalOrderNo) || number.equals(parent.brokerOrderNo)
                || !same(parent.plan.quantity(),c.plan.quantity()) || !parent.plan.stockCode().equals(c.plan.stockCode())
                || !parent.plan.market().equals(c.plan.market()) || !parent.plan.side().equals(c.plan.side())
                || !zero(original.filled) || !zero(original.openQuantity())) throw invalid();
            parentNo=original.orderNo;parentState=original.status;parentFilled=norm(original.filled);parentOpen=norm(original.openQuantity());
            if("AMEND".equals(c.kind)) {
                if(!"REPLACED".equals(original.status) || c.plan.limitPrice().compareTo(parent.plan.limitPrice())>=0 || !filled(child)) throw invalid();
                outcome="AMEND_FILLED";
            } else if("CANCEL".equals(c.kind)) {
                if(!"CANCELLED".equals(original.status) || !"CANCELLED".equals(child.status) || !zero(child.filled)
                    || !zero(child.openQuantity()) || !same(c.plan.limitPrice(),parent.plan.limitPrice())) throw invalid();
                outcome="CANCELLED";
            } else throw invalid();
        }
        return new Evidence("SIMULATION",c.id,c.kind,outcome,number,parentNo,c.plan.stockCode(),c.plan.market(),c.plan.side(),
            norm(c.plan.limitPrice()),norm(c.plan.quantity()),norm(child.filled),norm(child.openQuantity()),parentState,parentFilled,parentOpen);
    }
    public static boolean resolved(Command c){
        var r=c.completion;
        if(r==null || r.evidence()==null || r.tokenHash()==null || !r.tokenHash().matches("[0-9a-f]{64}") || r.confirmedAt()==null
            || r.resolutionId()==null || !"RETURNED".equals(c.dispatchPhase) || c.receipt==null || !c.receipt.valid()
            || !"UNKNOWN".equals(c.receipt.status()) || c.sendCount!=1 || c.executionKey==null || c.executionKey.isBlank()) return false;
        var e=r.evidence();
        if(!"SIMULATION".equals(e.source()) || !c.id.equals(e.commandId()) || !c.kind.equals(e.kind()) || !c.brokerOrderNo.equals(e.orderNo())
            || !c.plan.stockCode().equals(e.stockCode()) || !c.plan.market().equals(e.market()) || !c.plan.side().equals(e.side())
            || !same(c.plan.limitPrice(),e.price()) || !same(c.plan.quantity(),e.quantity()) || !"UNKNOWN".equals(c.status)) return false;
        try{LocalDateTime.parse(r.confirmedAt());}catch(RuntimeException exception){return false;}
        if(!zero(e.openQuantity()) || e.quantity()==null || e.quantity().signum()<=0 || e.quantity().stripTrailingZeros().scale()>0) return false;
        return switch(c.kind){
            case "NEW"->"FILLED".equals(e.outcome()) && c.parentId==null && same(e.quantity(),e.filledQuantity());
            case "AMEND"->"AMEND_FILLED".equals(e.outcome()) && c.parentId!=null && "REPLACED".equals(e.parentState())
                && !java.util.Objects.toString(e.parentOrderNo(),"").isBlank() && same(e.quantity(),e.filledQuantity()) && zero(e.parentFilled()) && zero(e.parentOpen());
            case "CANCEL"->"CANCELLED".equals(e.outcome()) && c.parentId!=null && "CANCELLED".equals(e.parentState())
                && !java.util.Objects.toString(e.parentOrderNo(),"").isBlank() && zero(e.filledQuantity()) && zero(e.parentFilled()) && zero(e.parentOpen());
            default->false;
        };
    }
    public static String digest(Evidence e){try{return OrderWorkflowRules.hash(new ObjectMapper().writeValueAsString(e));}catch(JsonProcessingException exception){throw new ApiException(ErrorCode.INTERNAL_ERROR);}}
    private static boolean filled(BrokerOrder b){return "FILLED".equals(b.status) && same(b.plan.quantity(),b.filled) && zero(b.openQuantity());}
    private static boolean zero(BigDecimal n){return n!=null && n.signum()==0;}
    private static BigDecimal norm(BigDecimal n){return n==null?null:n.stripTrailingZeros();}
    private static boolean same(BigDecimal a,BigDecimal b){return a!=null && b!=null && a.compareTo(b)==0;}
    private static boolean plan(OrderPrecheckRequest a,OrderPrecheckRequest b){return a!=null && b!=null && a.stockCode().equals(b.stockCode())
        && a.market().equals(b.market()) && a.side().equals(b.side()) && same(a.limitPrice(),b.limitPrice()) && same(a.quantity(),b.quantity());}
    private static ApiException invalid(){return new ApiException(ErrorCode.VALIDATION_ERROR,"[SIMULATION] 종료된 UNKNOWN 호출·가상 주문 소유권·전량 체결 또는 명시적 취소/대체를 확인하지 못했습니다. 차단은 유지됩니다.");}
    public record Evidence(String source,String commandId,String kind,String outcome,String orderNo,String parentOrderNo,String stockCode,String market,String side,
        BigDecimal price,BigDecimal quantity,BigDecimal filledQuantity,BigDecimal openQuantity,String parentState,BigDecimal parentFilled,BigDecimal parentOpen){}
}
