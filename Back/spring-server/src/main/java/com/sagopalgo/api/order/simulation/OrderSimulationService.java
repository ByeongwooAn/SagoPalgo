package com.sagopalgo.api.order.simulation;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.service.OrderSubmissionWorkflow;
import com.sagopalgo.api.order.service.OrderWorkflowRules;
import com.sagopalgo.api.order.service.OrderDispatchReceipt;
import com.sagopalgo.api.order.service.OrderSendingDiagnosticRules;
import com.sagopalgo.api.order.service.UnknownOrderReviewRules;
import com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse;
import com.sagopalgo.api.order.dto.KbOrderLookupResponse;
import com.sagopalgo.api.order.simulation.OrderSimulationState.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.*;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

/** 결정론적 가상 증권사입니다. KB/KIS 등 외부 클라이언트나 실계좌 데이터에 의존하지 않습니다. */
@Service
public class OrderSimulationService {
    public static final Set<String> SCENARIOS = Set.of("WAIT", "PARTIAL_FILL", "FULL_FILL", "REJECT",
        "TIMEOUT_BEFORE_ACCEPT", "TIMEOUT_AFTER_ACCEPT", "SAVE_FAILURE", "STOP_BEFORE_SEND", "JOURNAL_FAILURE",
        "TIMEOUT_AFTER_OPEN","TIMEOUT_AFTER_PARTIAL");
    private static final BigDecimal MAX_AMOUNT = new BigDecimal("1000000");
    private final OrderSimulationMapper mapper;
    private final OrderSimulationStore store;
    private final ObjectMapper json;

    public OrderSimulationService(OrderSimulationMapper mapper, OrderSimulationStore store, ObjectMapper json) {
        this.mapper = mapper; this.store = store; this.json = json;
    }

    public Map<String, Object> create(Long userId, BigDecimal cash) {
        if (cash == null || cash.signum() <= 0 || cash.scale() > 2 || cash.compareTo(new BigDecimal("1000000000")) > 0) {
            throw invalid("가상 시작 현금은 0원 초과 10억원 이하, 소수점 2자리까지 입력하세요.");
        }
        var state = new OrderSimulationState();
        state.cash = cash;
        state.quotes.put("KOSPI:005930", new BigDecimal("75000"));
        var id = UUID.randomUUID().toString();
        var now = OrderSimulationStore.now();
        event(state, "SESSION", "가상 현금과 가정 시세로 세션 생성. 실제 시세·실계좌가 아닙니다.");
        try { mapper.insert(new OrderSimulationMapper.Row(id, userId, store.encode(state), 0, now, now)); }
        catch (DataAccessException exception) { throw new ApiException(ErrorCode.SIMULATION_STORAGE_UNAVAILABLE); }
        return get(userId, id);
    }

    public List<Map<String, Object>> sessions(Long userId) {
        try { return mapper.recent(userId).stream().map(row -> Map.<String, Object>of("sessionId", row.sessionId(),
            "createdAt", row.createdAt().toString(), "mode", "SIMULATION")).toList(); }
        catch (DataAccessException exception) { throw new ApiException(ErrorCode.SIMULATION_STORAGE_UNAVAILABLE); }
    }

    public Map<String, Object> get(Long userId, String id) {
        OrderSimulationMapper.Row row;
        try { row = mapper.find(id, userId); }
        catch (DataAccessException exception) { throw new ApiException(ErrorCode.SIMULATION_STORAGE_UNAVAILABLE); }
        if (row == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        return view(id, row.revision(), store.decode(row.stateJson()));
    }

    public Map<String, Object> quote(Long userId, String id, String market, String code, BigDecimal price) {
        KbLimitOrderContract.requireSupported(new OrderPrecheckRequest(code, "가정 시세", market, "BUY", price, BigDecimal.ONE));
        store.mutate(userId, id, state -> {
            state.quotes.put(key(market, code), price);
            event(state, "QUOTE", "가정 시세 변경 " + code + " " + price + "원"); return null;
        });
        return get(userId, id);
    }

    public Map<String, Object> prepare(Long userId, String id, OrderPrecheckRequest requested, String kind,
        String parentId, String scenario) {
        if (!SCENARIOS.contains(scenario) || !Set.of("NEW", "AMEND", "CANCEL").contains(kind)) throw invalid("모의 시나리오/주문 종류가 올바르지 않습니다.");
        if ("CANCEL".equals(kind) && Set.of("PARTIAL_FILL", "FULL_FILL","TIMEOUT_AFTER_PARTIAL","TIMEOUT_AFTER_OPEN").contains(scenario)) throw invalid("취소는 체결 시나리오 대신 대기·거절·접수 후 응답 유실 시나리오를 선택하세요.");
        String token = OrderWorkflowRules.issueToken();
        String commandId = store.mutate(userId, id, state -> {
            if (state.commands.size() >= 100) throw invalid("세션의 명령 100건 한도입니다. 새 세션을 만드세요.");
            OrderPrecheckRequest plan;
            if ("NEW".equals(kind)) {
                if (parentId != null) throw invalid("신규 주문에는 원주문을 지정할 수 없습니다.");
                KbLimitOrderContract.requireSupported(requested);
                plan = normalized(requested);
            } else {
                var parent = changeable(state, parentId);
                BigDecimal price = "AMEND".equals(kind) ? requested.limitPrice() : parent.plan.limitPrice();
                plan = new OrderPrecheckRequest(parent.plan.stockCode(), parent.plan.stockName(), parent.plan.market(),
                    parent.plan.side(), price, parent.plan.quantity());
                if ("AMEND".equals(kind) && (price == null || price.compareTo(parent.plan.limitPrice()) >= 0)) throw invalid("실주문과 동일하게 지정가 인하만 지원합니다.");
            }
            KbLimitOrderContract.requireSupported(plan);
            if (Set.of("PARTIAL_FILL","TIMEOUT_AFTER_PARTIAL").contains(scenario) && !"CANCEL".equals(kind) && plan.quantity().compareTo(new BigDecimal("2")) < 0) {
                throw invalid("부분체결 시나리오는 정수 2주 이상 필요합니다.");
            }
            validate(state, plan, kind);
            var command = new Command();
            command.id = UUID.randomUUID().toString(); command.parentId = parentId; command.kind = kind;
            command.plan = plan; command.scenario = scenario; command.tokenHash = OrderWorkflowRules.hash(token);
            command.createdAt = OrderSimulationStore.now().toString();
            command.expiresAt = OrderSimulationStore.now().plusSeconds(OrderWorkflowRules.APPROVAL_SECONDS).toString();
            state.commands.put(command.id, command); event(state, command.id, "PREPARED: 공통 형식·금액 한도·시세 이탈률·가상 자원 검증 통과");
            return command.id;
        });
        return Map.of("mode", "SIMULATION", "commandId", commandId, "token", token, "snapshot", get(userId, id));
    }

    public Map<String, Object> confirm(Long userId, String id, String commandId, String token, boolean acknowledged) {
        store.mutate(userId, id, state -> {
            var c = command(state, commandId);
            if (!acknowledged || !"PREPARED".equals(c.status) || !OrderWorkflowRules.validToken(token, c.tokenHash,
                LocalDateTime.parse(c.expiresAt), OrderSimulationStore.now())) throw invalid("승인 확인이 만료되었거나 이미 사용되었습니다.");
            c.status = "READY";
            c.expiresAt = OrderSimulationStore.now().plusSeconds(OrderWorkflowRules.APPROVAL_SECONDS).toString();
            event(state, commandId, "READY: 승인 기록 저장, 아직 모의 전송하지 않음"); return null;
        });
        return get(userId, id);
    }

    public Map<String, Object> submit(Long userId, String id, String commandId, boolean acknowledged, String confirmation) {
        if (!acknowledged || !"모의 주문 전송".equals(confirmation)) throw invalid("모의 주문 최종 확인이 필요합니다.");
        var existing = command(readState(userId, id), commandId);
        if (Set.of("SENDING", "ACCEPTED", "REJECTED", "UNKNOWN").contains(existing.status)) return get(userId, id);
        String executionKey=UUID.randomUUID().toString();
        return OrderSubmissionWorkflow.execute(() -> {
            claim(userId,id,commandId,executionKey);
            if("STOP_BEFORE_SEND".equals(existing.scenario)) throw new ApiException(ErrorCode.SIMULATION_RESULT_FAILURE);
        }, () -> {
            store.mutate(userId,id,state -> {
                var c=command(state,commandId);
                if(!executionKey.equals(c.executionKey) || !"RESERVED".equals(c.dispatchPhase)) throw invalid("전송 소유권이 다릅니다.");
                c.dispatchPhase="DISPATCHING"; c.startedAt=OrderSimulationStore.now().toString(); return null;
            });
            return gateway(userId,id,commandId);
        }, outcome -> persist(userId,id,commandId,executionKey,outcome), () -> get(userId,id));
    }

    private void claim(Long userId, String id, String commandId, String executionKey) {
        store.mutate(userId, id, state -> {
            var c = command(state, commandId);
            if (!"READY".equals(c.status) || !LocalDateTime.parse(c.expiresAt).isAfter(OrderSimulationStore.now())) throw invalid("모의 제출 승인이 만료·사용되었습니다.");
            if (state.commands.values().stream().anyMatch(x -> Set.of("SENDING", "UNKNOWN").contains(x.status))) {
                throw invalid("미확정 모의 전송이 있습니다. 기록은 유지하고 다른 시나리오는 새 세션에서 실행하세요.");
            }
            validate(state, c.plan, c.kind);
            if ("NEW".equals(c.kind)) KbLimitOrderContract.encode(c.plan);
            else KbLimitOrderContract.encodeChange(c.plan, c.kind, command(state, c.parentId).brokerOrderNo);
            if (!"NEW".equals(c.kind)) changeable(state, c.parentId).changed = true;
            c.status = "SENDING";
            c.executionKey=executionKey; c.dispatchPhase="RESERVED";
            event(state, commandId, "SENDING: 제출 가드 커밋, 재전송 금지"); return null;
        });
    }

    /** 네트워크 없이 가상 증권사 상태를 커밋한 뒤 성공/거절/응답 유실을 반환합니다. */
    private KbLimitOrderContract.Outcome gateway(Long userId, String id, String commandId) {
        String scenario = command(readState(userId, id), commandId).scenario;
        if ("TIMEOUT_BEFORE_ACCEPT".equals(scenario)) {
            store.mutate(userId, id, state -> { command(state, commandId).sendCount++; event(state, commandId, "모의 전송 1회: 접수 전 응답 유실"); return null; });
            throw new IllegalStateException("simulated timeout before accept");
        }
        var outcome = store.mutate(userId, id, state -> {
            var c = command(state, commandId); c.sendCount++;
            if ("NEW".equals(c.kind)) KbLimitOrderContract.encode(c.plan);
            else KbLimitOrderContract.encodeChange(c.plan, c.kind, command(state, c.parentId).brokerOrderNo);
            if ("REJECT".equals(scenario)) { event(state, commandId, "가상 증권사 명시적 거절"); return interpreted(false, "0000000000"); }
            BrokerOrder parentOrder = null;
            if (!"NEW".equals(c.kind)) {
                var parent = command(state, c.parentId); parentOrder = state.brokerOrders.get(parent.brokerOrderNo);
                if (parentOrder == null || !"OPEN".equals(parentOrder.status)) return interpreted(false, "0000000000");
            }
            String orderNo = String.format(java.util.Locale.ROOT, "%010d", state.sequence++);
            var broker = new BrokerOrder(); broker.orderNo = orderNo; broker.commandId = commandId; broker.plan = c.plan;
            if (parentOrder != null) parentOrder.status = "CANCEL".equals(c.kind) ? "CANCELLED" : "REPLACED";
            if ("CANCEL".equals(c.kind)) broker.status = "CANCELLED";
            state.brokerOrders.put(orderNo, broker);
            // 응답 유실 시에도 증권사 쪽 접수 여부를 시험할 수 있도록 내부 가정 상태를 별도로 보관합니다.
            c.brokerOrderNo = orderNo;
            if (!"CANCEL".equals(c.kind)) {
                if (Set.of("FULL_FILL", "TIMEOUT_AFTER_ACCEPT").contains(scenario)) fill(state, broker, c.plan.quantity());
                else if (Set.of("PARTIAL_FILL","TIMEOUT_AFTER_PARTIAL").contains(scenario)) fill(state, broker, c.plan.quantity().divideToIntegralValue(new BigDecimal("2")));
            }
            event(state, commandId, "가상 증권사 접수 " + orderNo + " · " + broker.status);
            return interpreted(true, orderNo);
        });
        if (Set.of("TIMEOUT_AFTER_ACCEPT","TIMEOUT_AFTER_OPEN","TIMEOUT_AFTER_PARTIAL").contains(scenario)
            && outcome.status() == KbLimitOrderContract.Status.ACCEPTED) throw new IllegalStateException("simulated timeout after accept");
        return outcome;
    }

    private void persist(Long userId, String id, String commandId, String executionKey, KbLimitOrderContract.Outcome outcome) {
        var c = command(readState(userId, id), commandId);
        if ("JOURNAL_FAILURE".equals(c.scenario)) throw new ApiException(ErrorCode.SIMULATION_RESULT_FAILURE);
        var receipt=OrderDispatchReceipt.from(outcome);
        store.mutate(userId,id,state -> {
            var current=command(state,commandId);
            if(!executionKey.equals(current.executionKey) || !Set.of("RESERVED","DISPATCHING").contains(current.dispatchPhase)) {
                throw invalid("전송 결과 기록 소유권이 다릅니다.");
            }
            if("RESERVED".equals(current.dispatchPhase) && !"UNKNOWN".equals(receipt.status())) throw invalid("전송 시작 기록이 없습니다.");
            current.receipt=receipt; current.dispatchPhase="RETURNED"; current.returnedAt=OrderSimulationStore.now().toString();
            event(state,commandId,"RETURNED: 호출 종료 결과 별도 저장 · " + receipt.status()); return null;
        });
        if ("SAVE_FAILURE".equals(c.scenario)) throw new ApiException(ErrorCode.SIMULATION_RESULT_FAILURE);
        store.mutate(userId, id, state -> {
            var current = command(state, commandId);
            if(receipt.status().equals(current.status)) return null;
            OrderDispatchReceipt.requireReplayable(current.status,current.dispatchPhase,current.receipt);
            current.status = receipt.status();
            event(state, commandId, "클라이언트 결과 " + current.status); return null;
        });
    }

    public Map<String,Object> recover(Long userId,String id,String commandId,boolean acknowledged,String confirmation) {
        if(!acknowledged || !"저장된 전송 결과 복구".equals(confirmation)) throw invalid("추가 전송 없는 기록 복구임을 확인하세요.");
        store.mutate(userId,id,state -> {
            var c=command(state,commandId);
            if(c.receipt!=null && c.receipt.valid() && "RETURNED".equals(c.dispatchPhase) && c.receipt.status().equals(c.status)) return null;
            OrderDispatchReceipt.requireReplayable(c.status,c.dispatchPhase,c.receipt);
            c.status=c.receipt.status(); c.recoveredAt=OrderSimulationStore.now().toString();
            event(state,commandId,"저장 결과로 " + c.status + " 복구. 추가 전송·가상 체결 없음"); return null;
        });
        return get(userId,id);
    }

    public Map<String, Object> fill(Long userId, String id, String orderNo, BigDecimal quantity) {
        store.mutate(userId, id, state -> {
            var order = state.brokerOrders.get(orderNo);
            if (order == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
            fill(state, order, quantity); return null;
        });
        return get(userId, id);
    }

    public Diagnostic diagnose(Long userId,String id,String commandId,String diagnosticId,String orderNo,boolean acknowledged,String confirmation) {
        OrderSendingDiagnosticRules.validate(diagnosticId,orderNo,acknowledged,confirmation);
        return store.mutate(userId,id,state -> {
            var c=command(state,commandId);
            for(var candidate:state.commands.values()) for(var previous:candidate.diagnostics) {
                if(diagnosticId.equals(previous.diagnosticId())) {
                    if(!commandId.equals(previous.commandId()) || !orderNo.equals(previous.orderNo())) throw invalid("같은 진단 ID의 조회 대상을 바꿀 수 없습니다.");
                    return previous;
                }
            }
            String phase=c.dispatchPhase==null?"LEGACY_UNVERIFIED":c.dispatchPhase;
            OrderSendingDiagnosticRules.requireCandidate(c.status,phase);
            if(c.diagnostics.size()>=20) throw invalid("명령당 진단 20건 한도입니다. 저장 이력을 확인하세요.");
            var broker=state.brokerOrders.get(orderNo);
            List<KbOrderExecutionItemResponse> rows=List.of();
            if(broker!=null) {
                var plan=broker.plan;
                String time=LocalDateTime.parse(command(state,broker.commandId).createdAt).format(java.time.format.DateTimeFormatter.ofPattern("HHmmss"));
                rows=List.of(new KbOrderExecutionItemResponse(orderNo,plan.stockCode(),"","BUY".equals(plan.side())?"매수":"매도",time,
                    plan.quantity(),broker.filled,broker.openQuantity(),plan.limitPrice(),null,"",broker.status));
            }
            var created=LocalDateTime.parse(c.createdAt);
            String date=created.toLocalDate().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE);
            var report=OrderSendingDiagnosticRules.evaluate(c.plan,c.kind,date,created,orderNo,new KbOrderLookupResponse(date,orderNo,true,1,rows))
                .after(phase,c.status,true);
            String now=OrderSimulationStore.now().toString();
            var diagnostic=new Diagnostic(diagnosticId,commandId,orderNo,phase,"COMPLETED",report,now,now);
            c.diagnostics.add(diagnostic);
            event(state,commandId,"잠금 유지 진단 " + report.assessment() + " · 추가 전송·상태 변경 없음");
            return diagnostic;
        });
    }

    public Map<String,Object> prepareReview(Long user,String session,String commandId,String orderNo) {
        UnknownOrderReviewRules.number(orderNo);String token=OrderWorkflowRules.issueToken();
        var prepared=store.mutate(user,session,state->{
            var c=command(state,commandId);UnknownOrderReviewRules.candidate(c.status);
            if(c.reviews.size()>=20) throw invalid("명령당 대조 관찰 20건 한도입니다.");
            var evidence=reviewEvidence(state,c,orderNo);
            var preparation=new ReviewPreparation(UUID.randomUUID().toString(),OrderWorkflowRules.hash(token),UnknownOrderReviewRules.digest(evidence),
                OrderSimulationStore.now().plusSeconds(90).toString(),evidence);
            c.reviewPreparation=preparation;event(state,commandId,"UNKNOWN 대조 준비 · 차단 유지");return preparation;
        });
        return Map.of("reviewId",prepared.reviewId(),"token",token,"expiresAt",prepared.expiresAt(),"evidence",prepared.evidence(),"message",UnknownOrderReviewRules.MESSAGE);
    }
    public Map<String,Object> confirmReview(Long user,String session,String commandId,String reviewId,String token,boolean acknowledged,String confirmation) {
        UnknownOrderReviewRules.acknowledge(acknowledged,confirmation);
        if(token==null || token.length()>200) throw invalid("대조 토큰을 확인하세요.");
        store.mutate(user,session,state->{
            var c=command(state,commandId);String hash=OrderWorkflowRules.hash(token);
            var previous=c.reviews.stream().filter(r->r.reviewId().equals(reviewId)).findFirst().orElse(null);
            if(previous!=null){if(!previous.tokenHash().equals(hash)) throw invalid("대조 토큰이 다릅니다.");return null;}
            UnknownOrderReviewRules.candidate(c.status);var prepared=c.reviewPreparation;
            if(prepared==null || !prepared.reviewId().equals(reviewId) || !OrderWorkflowRules.validToken(token,prepared.tokenHash(),
                LocalDateTime.parse(prepared.expiresAt()),OrderSimulationStore.now())) throw invalid("대조 확인이 만료·변경되었습니다.");
            var evidence=reviewEvidence(state,c,prepared.evidence().orderNo());
            if(!UnknownOrderReviewRules.digest(evidence).equals(prepared.evidenceHash())) throw invalid("조회 관찰이 바뀌었습니다. 다시 준비하세요.");
            c.reviews.add(new StoredReview(reviewId,hash,evidence,OrderSimulationStore.now().toString()));c.reviewPreparation=null;
            event(state,commandId,"UNKNOWN 대조 관찰 저장 · 차단·가상 자원·전송 횟수 유지");return null;
        });
        return get(user,session);
    }
    private UnknownOrderReviewRules.Evidence reviewEvidence(OrderSimulationState state,Command c,String orderNo) {
        var broker=state.brokerOrders.get(orderNo);List<KbOrderExecutionItemResponse> rows=List.of();
        String parent="NEW".equals(c.kind)?"":command(state,c.parentId).brokerOrderNo;
        if(broker!=null){
            var source=command(state,broker.commandId);var p=broker.plan;
            String original="NEW".equals(source.kind)?"":command(state,source.parentId).brokerOrderNo;
            rows=List.of(new KbOrderExecutionItemResponse(orderNo,p.stockCode(),"","BUY".equals(p.side())?"매수":"매도",
                LocalDateTime.parse(source.createdAt).format(java.time.format.DateTimeFormatter.ofPattern("HHmmss")),p.quantity(),broker.filled,
                broker.openQuantity(),p.limitPrice(),null,"",broker.status,original,"NEW".equals(source.kind)?"":"SIM_"+source.kind,
                "AMEND".equals(source.kind)?p.quantity():BigDecimal.ZERO,BigDecimal.ZERO));
        }
        var created=LocalDateTime.parse(c.createdAt);String date=created.toLocalDate().format(java.time.format.DateTimeFormatter.BASIC_ISO_DATE);
        return UnknownOrderReviewRules.verify(c.plan,c.kind,date,created,parent,orderNo,new KbOrderLookupResponse(date,orderNo,true,1,rows));
    }

    private void fill(OrderSimulationState state, BrokerOrder order, BigDecimal quantity) {
        if (quantity == null || quantity.signum() <= 0 || quantity.stripTrailingZeros().scale() > 0
            || order.openQuantity().compareTo(quantity) < 0) throw invalid("체결 수량은 남은 미체결 이내의 양수 정수여야 합니다.");
        String key = key(order.plan.market(), order.plan.stockCode());
        BigDecimal amount = order.plan.limitPrice().multiply(quantity);
        BigDecimal position = state.positions.getOrDefault(key, BigDecimal.ZERO);
        if ("BUY".equals(order.plan.side())) { state.cash = state.cash.subtract(amount); state.positions.put(key, position.add(quantity)); }
        else { state.cash = state.cash.add(amount); state.positions.put(key, position.subtract(quantity)); }
        order.filled = order.filled.add(quantity);
        order.status = order.filled.compareTo(order.plan.quantity()) == 0 ? "FILLED" : "PARTIAL";
        event(state, order.commandId, "수동 가상 체결 " + quantity + "주 · " + order.status);
    }

    private Command changeable(OrderSimulationState state, String parentId) {
        var parent = command(state, parentId);
        OrderWorkflowRules.requireChangeable(parent.kind, parent.status, parent.changed,
            parent.createdAt.substring(0, 10).equals(OrderSimulationStore.now().toLocalDate().toString()));
        var order = state.brokerOrders.get(parent.brokerOrderNo);
        if (order == null || !"OPEN".equals(order.status) || order.filled.signum() != 0) throw invalid("실주문과 동일하게 전량 미체결 주문만 변경할 수 있습니다.");
        return parent;
    }

    private void validate(OrderSimulationState state, OrderPrecheckRequest plan, String kind) {
        KbLimitOrderContract.requireSupported(plan);
        if ("CANCEL".equals(kind)) return;
        BigDecimal quote = state.quotes.get(key(plan.market(), plan.stockCode()));
        if (quote == null || quote.signum() <= 0 || OrderWorkflowRules.deviation(plan.limitPrice(), quote).compareTo(new BigDecimal("5")) > 0
            || plan.limitPrice().multiply(plan.quantity()).compareTo(MAX_AMOUNT) > 0) throw invalid("가정 시세·이탈률 5%·1회 100만원 한도를 확인하세요.");
        if ("NEW".equals(kind)) {
            BigDecimal available = "BUY".equals(plan.side()) ? availableCash(state) : availableShares(state, key(plan.market(), plan.stockCode()));
            BigDecimal required = "BUY".equals(plan.side()) ? plan.limitPrice().multiply(plan.quantity()) : plan.quantity();
            if (!OrderWorkflowRules.covers(available, required)) throw invalid("예약분을 제외한 가상 현금/주식이 부족합니다.");
        }
    }

    private BigDecimal availableCash(OrderSimulationState state) {
        return state.brokerOrders.values().stream().filter(o -> "BUY".equals(o.plan.side()))
            .map(o -> o.openQuantity().multiply(o.plan.limitPrice())).reduce(state.cash, BigDecimal::subtract);
    }
    private BigDecimal availableShares(OrderSimulationState state, String key) {
        return state.brokerOrders.values().stream().filter(o -> "SELL".equals(o.plan.side()) && key.equals(key(o.plan.market(), o.plan.stockCode())))
            .map(BrokerOrder::openQuantity).reduce(state.positions.getOrDefault(key, BigDecimal.ZERO), BigDecimal::subtract);
    }

    private OrderSimulationState readState(Long userId, String id) {
        var row = mapper.find(id, userId);
        if (row == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        return store.decode(row.stateJson());
    }
    private Command command(OrderSimulationState state, String id) {
        var command = state.commands.get(id);
        if (command == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND); return command;
    }
    private Map<String, Object> view(String id, long revision, OrderSimulationState state) {
        List<Map<String, Object>> commands = new ArrayList<>();
        // MySQL JSON 객체의 키 순서는 삽입 순서가 아니므로 생성 시각으로 다시 정렬합니다.
        for (var c : state.commands.values().stream().sorted(Comparator.comparing((Command c) -> c.createdAt).thenComparing(c -> c.id)).toList()) {
            var broker = state.brokerOrders.get(c.brokerOrderNo);
            var item = new LinkedHashMap<String, Object>();
            item.put("id", c.id); item.put("kind", c.kind); item.put("parentId", c.parentId); item.put("plan", c.plan);
            item.put("scenario", c.scenario); item.put("status", c.status); item.put("expiresAt", c.expiresAt);
            item.put("expired", Set.of("PREPARED", "READY").contains(c.status) && !LocalDateTime.parse(c.expiresAt).isAfter(OrderSimulationStore.now()));
            item.put("createdAt", c.createdAt); item.put("changed", c.changed); item.put("sendCount", c.sendCount);
            item.put("dispatchPhase",c.dispatchPhase==null?"LEGACY_UNVERIFIED":c.dispatchPhase);
            item.put("receipt",c.receipt); item.put("startedAt",c.startedAt); item.put("returnedAt",c.returnedAt); item.put("recoveredAt",c.recoveredAt);
            item.put("recoverable","SENDING".equals(c.status) && "RETURNED".equals(c.dispatchPhase) && c.receipt!=null && c.receipt.valid());
            item.put("diagnostics",List.copyOf(c.diagnostics));
            item.put("reviews",c.reviews.stream().map(r->Map.of("reviewId",r.reviewId(),"evidence",r.evidence(),
                "confirmedAt",r.confirmedAt(),"lockMaintained",true,"message",UnknownOrderReviewRules.MESSAGE)).toList());
            item.put("brokerOrderNo", c.brokerOrderNo); item.put("brokerStatus", broker == null ? "NONE" : broker.status);
            item.put("filledQuantity", broker == null ? BigDecimal.ZERO : broker.filled);
            item.put("openQuantity", broker == null ? BigDecimal.ZERO : broker.openQuantity()); commands.add(item);
        }
        return Map.of("mode", "SIMULATION", "sessionId", id, "revision", revision, "cash", state.cash,
            "availableCash", availableCash(state), "positions", state.positions, "quotes", state.quotes,
            "commands", commands, "events", state.events,
            "blocked", state.commands.values().stream().anyMatch(c -> Set.of("SENDING", "UNKNOWN").contains(c.status)));
    }
    private KbLimitOrderContract.Outcome interpreted(boolean accepted, String orderNo) {
        return KbLimitOrderContract.interpret(json.valueToTree(Map.of("dataHeader", Map.of("resultCode", "200", "processFlag", accepted ? "A" : "B"),
            "dataBody", Map.of("ordr_no", orderNo))));
    }
    private OrderPrecheckRequest normalized(OrderPrecheckRequest p) {
        if (p.stockName() == null || p.stockName().isBlank() || p.stockName().length() > 100) throw invalid("종목명은 1~100자로 입력하세요.");
        return new OrderPrecheckRequest(p.stockCode().trim(), p.stockName().trim(), p.market().trim().toUpperCase(Locale.ROOT),
            p.side().trim().toUpperCase(Locale.ROOT), p.limitPrice(), p.quantity());
    }
    private String key(String market, String code) { return market.trim().toUpperCase(Locale.ROOT) + ":" + code.trim(); }
    private void event(OrderSimulationState state, String command, String message) {
        if (state.events.size() >= 1000) throw invalid("세션 이벤트 한도입니다. 기록은 유지하고 새 세션에서 시험하세요.");
        state.events.add(Map.of("at", OrderSimulationStore.now().toString(), "commandId", command, "message", message));
    }
    private ApiException invalid(String message) { return new ApiException(ErrorCode.VALIDATION_ERROR, message); }
}
