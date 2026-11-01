package com.sagopalgo.api.order.simulation;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.service.OrderReservationBudget;
import com.sagopalgo.api.order.simulation.OrderSimulationState.*;
import java.math.BigDecimal;
import java.util.*;

/** 가상 원장에서만 소유권·변경 배분·잔량을 입증합니다. 실제 KB 자원에는 적용하지 않습니다. */
public final class SimulationChangeRules {
    private SimulationChangeRules() {}
    public static BrokerOrder source(OrderSimulationState state,Command parent) {
        if(parent==null || !Set.of("NEW","AMEND").contains(parent.kind) || !"ACCEPTED".equals(parent.status)
            || parent.sendCount!=1 || parent.executionKey==null || !"RETURNED".equals(parent.dispatchPhase)
            || parent.receipt==null || !parent.receipt.valid() || !"ACCEPTED".equals(parent.receipt.status())
            || !Objects.equals(parent.brokerOrderNo,parent.receipt.orderNo())
            || parent.createdAt==null || !parent.createdAt.substring(0,10).equals(OrderSimulationStore.now().toLocalDate().toString())) throw invalid();
        var b=state.brokerOrders.get(parent.brokerOrderNo);
        if(!owns(parent,b) || !Set.of("OPEN","PARTIAL").contains(b.status) || !OrderReservationBudget.whole(b.filled)
            || !OrderReservationBudget.whole(b.removed) || b.openQuantity().signum()<=0 || !allocationConsistent(b)) throw invalid();
        if("AMEND".equals(parent.kind) && !linked(state,parent)) throw invalid();
        if(parent.changed) {
            var previous=state.commands.get(parent.latestChangeId);
            if(previous==null || !"ACCEPTED".equals(previous.status) || !parent.id.equals(previous.parentId) || !linked(state,previous)) throw invalid();
        }
        return b;
    }
    public static boolean canChange(OrderSimulationState state,Command c){try{source(state,c);return true;}catch(RuntimeException exception){return false;}}
    public static ChangeSnapshot snapshot(Command parent,BrokerOrder b) {
        return new ChangeSnapshot(b.orderNo,n(b.filled),n(b.removed),n(b.openQuantity()),b.revision,parent.latestChangeId);
    }
    public static boolean snapshotMatches(Command parent,BrokerOrder b,ChangeSnapshot prepared,boolean claimed,String childId) {
        if(prepared==null || !owns(parent,b)) return false;
        var current=snapshot(parent,b);
        return Objects.equals(claimed?childId:prepared.previousChangeId(),parent.latestChangeId)
            && Objects.equals(current.parentOrderNo(),prepared.parentOrderNo()) && current.revision()==prepared.revision()
            && same(current.filledQuantity(),prepared.filledQuantity()) && same(current.removedQuantity(),prepared.removedQuantity())
            && same(current.openQuantity(),prepared.openQuantity());
    }
    public static boolean canAllocate(Command parent,BrokerOrder b,Command child) {
        if(!owns(parent,b) || !Set.of("OPEN","PARTIAL").contains(b.status) || b.openQuantity().compareTo(child.plan.quantity())<0) return false;
        if(child.changeSnapshot!=null) return snapshotMatches(parent,b,child.changeSnapshot,true,child.id);
        // 이전 승인에는 부분체결/부분 배분 지원을 소급 부여하지 않습니다.
        return "OPEN".equals(b.status) && b.filled.signum()==0 && same(parent.plan.quantity(),child.plan.quantity());
    }
    public static boolean owns(Command c,BrokerOrder b) {
        return c!=null && b!=null && Objects.equals(c.id,b.commandId) && Objects.equals(c.brokerOrderNo,b.orderNo)
            && Objects.equals(c.kind,b.changeKind) && samePlan(c.plan,b.plan);
    }
    public static boolean linked(OrderSimulationState state,Command child) {
        if(child==null || child.sendCount!=1 || child.executionKey==null || child.executionKey.isBlank()
            || !"RETURNED".equals(child.dispatchPhase) || child.receipt==null || !child.receipt.valid()
            || !Objects.equals(child.status,child.receipt.status())
            || ("ACCEPTED".equals(child.status) && !Objects.equals(child.brokerOrderNo,child.receipt.orderNo()))) return false;
        var parent=state.commands.get(child.parentId);if(parent==null) return false;
        var original=state.brokerOrders.get(parent.brokerOrderNo);var b=state.brokerOrders.get(child.brokerOrderNo);
        if(!owns(parent,original) || !owns(child,b) || !Objects.equals(original.orderNo,b.originalOrderNo)
            || original.orderNo.equals(b.orderNo) || !parent.plan.stockCode().equals(child.plan.stockCode())
            || !parent.plan.market().equals(child.plan.market()) || !parent.plan.side().equals(child.plan.side())) return false;
        if(child.changeSnapshot!=null) return allocationConsistent(original)
            && same(original.changeAllocations.get(child.id),child.plan.quantity())
            && Objects.equals(child.changeSnapshot.parentOrderNo(),original.orderNo)
            && child.changeSnapshot.openQuantity().compareTo(child.plan.quantity())>=0;
        // 기존 전량 변경의 저장 근거만 허용합니다. 누락된 소유권을 새로 만들지 않습니다.
        return original.changeAllocations.isEmpty() && "NEW".equals(parent.kind) && parent.changed
            && Objects.equals(original.changedByCommandId,child.id) && same(parent.plan.quantity(),child.plan.quantity())
            && original.filled.signum()==0 && Set.of("REPLACED","CANCELLED").contains(original.status);
    }
    private static boolean allocationConsistent(BrokerOrder b) {
        if(b.changeAllocations==null || b.removed==null || b.plan==null || !OrderReservationBudget.whole(b.removed)
            || !OrderReservationBudget.whole(b.filled)) return false;
        BigDecimal sum=BigDecimal.ZERO;
        for(var q:b.changeAllocations.values()){if(!OrderReservationBudget.whole(q) || q.signum()<=0)return false;sum=sum.add(q);}
        return same(sum,b.removed) && b.filled.add(b.removed).compareTo(b.plan.quantity())<=0;
    }
    public static boolean samePlan(OrderPrecheckRequest a,OrderPrecheckRequest b){return a!=null && b!=null
        && Objects.equals(a.stockCode(),b.stockCode()) && Objects.equals(a.market(),b.market()) && Objects.equals(a.side(),b.side())
        && same(a.limitPrice(),b.limitPrice()) && same(a.quantity(),b.quantity());}
    private static boolean same(BigDecimal a,BigDecimal b){return a!=null && b!=null && a.compareTo(b)==0;}
    private static BigDecimal n(BigDecimal value){return value.stripTrailingZeros();}
    private static ApiException invalid(){return new ApiException(ErrorCode.VALIDATION_ERROR,"가상 주문의 소유권·현재 잔량·이전 변경 접수를 확인하지 못했습니다. 불명확·거절·이전 형식의 변경 가드는 유지합니다.");}
}
