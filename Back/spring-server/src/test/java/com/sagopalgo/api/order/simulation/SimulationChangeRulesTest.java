package com.sagopalgo.api.order.simulation;

import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.simulation.OrderSimulationState.*;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

class SimulationChangeRulesTest {
    @Test void legacyApprovalCannotAllocateFullQuantityAfterAnInterveningFill() {
        var parent=new Command();parent.id="parent";parent.kind="NEW";parent.brokerOrderNo="0000000001";parent.plan=plan("2");
        var order=new BrokerOrder();order.commandId=parent.id;order.changeKind="NEW";order.orderNo=parent.brokerOrderNo;order.plan=parent.plan;
        var child=new Command();child.id="child";child.kind="AMEND";child.plan=plan("2");
        assertThat(SimulationChangeRules.canAllocate(parent,order,child)).isTrue();
        order.status="PARTIAL";order.filled=BigDecimal.ONE;
        assertThat(SimulationChangeRules.canAllocate(parent,order,child)).isFalse();
        child.plan=plan("1"); // 수량이 맞아도 과거 승인에 부분 변경 권한을 만들지 않습니다.
        assertThat(SimulationChangeRules.canAllocate(parent,order,child)).isFalse();
    }
    private OrderPrecheckRequest plan(String quantity){return new OrderPrecheckRequest("005930","삼성전자","KOSPI","BUY",new BigDecimal("75000"),new BigDecimal(quantity));}
}
