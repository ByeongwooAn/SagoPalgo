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
        public String latestChangeId;
        public ChangeSnapshot changeSnapshot;
        public int sendCount;
        public String executionKey;
        public String dispatchPhase;
        public com.sagopalgo.api.order.service.OrderDispatchReceipt receipt;
        public String startedAt;
        public String returnedAt;
        public String recoveredAt;
        public List<Diagnostic> diagnostics = new ArrayList<>();
        public ReviewPreparation reviewPreparation;
        public List<StoredReview> reviews = new ArrayList<>();
        public CompletionPreparation completionPreparation;
        public StoredCompletion completion;
    }

    public record Diagnostic(String diagnosticId,String commandId,String orderNo,String phaseBefore,String state,
        com.sagopalgo.api.order.service.OrderSendingDiagnosticRules.Report report,String createdAt,String completedAt){}
    public record ReviewPreparation(String reviewId,String tokenHash,String evidenceHash,String expiresAt,
        com.sagopalgo.api.order.service.UnknownOrderReviewRules.Evidence evidence){}
    public record StoredReview(String reviewId,String tokenHash,com.sagopalgo.api.order.service.UnknownOrderReviewRules.Evidence evidence,String confirmedAt){}
    public record CompletionPreparation(String resolutionId,String tokenHash,String evidenceHash,String expiresAt,SimulationCompletionRules.Evidence evidence){}
    public record StoredCompletion(String resolutionId,String tokenHash,SimulationCompletionRules.Evidence evidence,String confirmedAt){}
    public record ChangeSnapshot(String parentOrderNo,BigDecimal filledQuantity,BigDecimal removedQuantity,
        BigDecimal openQuantity,long revision,String previousChangeId){}

    public static class BrokerOrder {
        public String orderNo;
        public String commandId;
        public OrderPrecheckRequest plan;
        public String status = "OPEN";
        public BigDecimal filled = BigDecimal.ZERO;
        public BigDecimal removed = BigDecimal.ZERO;
        public long revision;
        public Map<String,BigDecimal> changeAllocations = new LinkedHashMap<>();
        public String originalOrderNo;
        public String changeKind;
        public String changedByCommandId;
        public BigDecimal openQuantity() {
            return Set.of("OPEN", "PARTIAL").contains(status) ? plan.quantity().subtract(filled).subtract(removed) : BigDecimal.ZERO;
        }
    }
}
