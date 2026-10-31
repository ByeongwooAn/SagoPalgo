package com.sagopalgo.api.order.simulation;

import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import java.math.BigDecimal;
import java.util.*;

/** DB 내부 상태입니다. 토큰 해시를 포함하므로 API에는 view()로 투영한 데이터만 반환합니다. */
public class OrderSimulationState {
    public BigDecimal cash = BigDecimal.ZERO;
    public Map<String, BigDecimal> positions = new LinkedHashMap<>();
    public Map<String, BigDecimal> quotes = new LinkedHashMap<>();
    public Map<String, Command> commands = new LinkedHashMap<>();
    public Map<String, BrokerOrder> brokerOrders = new LinkedHashMap<>();
    public List<Map<String, String>> events = new ArrayList<>();
    public long sequence = 1;

    public static class Command {
        public String id;
        public String parentId;
        public String kind;
        public OrderPrecheckRequest plan;
        public String scenario;
        public String status = "PREPARED";
        public String tokenHash;
        public String expiresAt;
        public String createdAt;
        public String brokerOrderNo = "";
        public boolean changed;
        public int sendCount;
    }

    public static class BrokerOrder {
        public String orderNo;
        public String commandId;
        public OrderPrecheckRequest plan;
        public String status = "OPEN";
        public BigDecimal filled = BigDecimal.ZERO;
        public BigDecimal openQuantity() {
            return Set.of("OPEN", "PARTIAL").contains(status) ? plan.quantity().subtract(filled) : BigDecimal.ZERO;
        }
    }
}
