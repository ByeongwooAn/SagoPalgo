package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.dto.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;
import org.springframework.stereotype.Service;

/** 수동 주문만 처리. 재시도·가드 해제·포트폴리오 자동 변경은 하지 않습니다. */
@Service
public class ManualOrderService {
    private static final ZoneId KST=ZoneId.of("Asia/Seoul");
    private final ManualOrderMapper mapper;
    private final OrderPrecheckMapper prechecks;
    private final OrderPrecheckService precheckService;
    private final OrderAccountBinding binding;
    private final OrderReadinessService readiness;
    private final KbOrderExecutionService executions;
    private final KbSecuritiesAccountClient client;
    private final ManualOrderStore store;
    private final ManualOrderDispatchService dispatch;

    public ManualOrderService(ManualOrderMapper mapper, OrderPrecheckMapper prechecks, OrderPrecheckService precheckService,
        OrderAccountBinding binding, OrderReadinessService readiness, KbOrderExecutionService executions,
        KbSecuritiesAccountClient client, ManualOrderStore store, ManualOrderDispatchService dispatch) {
        this.mapper=mapper;this.prechecks=prechecks;this.precheckService=precheckService;this.binding=binding;
        this.readiness=readiness;this.executions=executions;this.client=client;this.store=store;
        this.dispatch=dispatch;
    }

    public List<ManualOrderResponse> history(Long user) {
        storage(); return mapper.recent(user).stream().map(c -> response(user,c)).toList();
    }
    public ManualOrderResponse get(Long user,String id) { return response(user,require(user,id)); }

    private ManualOrderResponse response(Long user,ManualOrderCommand command) {
        return ManualOrderResponse.from(command,mapper.reconciliation(command.commandId(),user));
    }

    public ManualOrderResponse submit(Long user,Long approvalId,boolean acknowledged,String confirmation) {
        acknowledge(acknowledged,confirmation);
        storage();
        ManualOrderCommand previous=mapper.findApproval(approvalId,user);
        if(previous!=null) return response(user,previous);
        ready();
        OrderPrecheckRecord plan=prechecks.findForApproval(approvalId,user);
        if(plan==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        OrderPrecheckRequest request=new OrderPrecheckRequest(plan.getStockCode(),plan.getStockName(),plan.getMarket(),
            plan.getOrderSide(),plan.getRequestedPrice(),plan.getQuantity());
        validateFresh(user,request);
        // 실제 제출 전 현재 연결에서 읽기 전용 주문 이력 접근이 가능한지도 다시 확인합니다.
        executions.page(today(),"0","");
        String fingerprint=binding.requireFingerprint();
        ManualOrderCommand command=command(user,approvalId,null,"NEW",request,fingerprint,null,"SENDING");
        // 승인 계좌 지문과 만료는 가드 SQL에서 다시 검증됩니다.
        return transmit(command,KbLimitOrderContract.encode(request));
    }

    public ChangePreparation prepareChange(Long user,String parentId,String kind,BigDecimal price) {
        ready();
        ManualOrderCommand parent=require(user,parentId);
        requireChangeable(parent);
        ManualOrderObservation observation=sync(user,parentId);
        if(!"OPEN".equals(observation.status())) throw new ApiException(ErrorCode.VALIDATION_ERROR,
            "전량 미체결이 확인된 당일 주문만 정정·취소할 수 있습니다. 부분체결·불명확한 주문은 KB 앱에서 확인하세요.");
        if(!Set.of("AMEND","CANCEL").contains(kind)) throw new ApiException(ErrorCode.VALIDATION_ERROR);
        BigDecimal newPrice="AMEND".equals(kind)?price:parent.price();
        OrderPrecheckRequest request=new OrderPrecheckRequest(parent.stockCode(),parent.stockName(),parent.market(),
            parent.side(),newPrice,parent.quantity());
        KbLimitOrderContract.requireSupported(request);
        // 정정은 신규 전체 금액에 대한 자원 검증 대신 실제 시세·한도 검증을 적용합니다.
        // 기존 주문 예약 자원으로 인해 조회 잔액은 차감되어 있을 수 있습니다.
        if("AMEND".equals(kind)) validateAmend(user,request,parent);
        String token=OrderWorkflowRules.issueToken();
        ManualOrderCommand child=command(user,null,parentId,kind,request,binding.requireFingerprint(),hash(token),"PREPARED");
        mapper.insert(child);
        return new ChangePreparation(ManualOrderResponse.from(child),token,child.expiresAt());
    }

    public ManualOrderResponse submitChange(Long user,String id,String token,boolean acknowledged,String confirmation) {
        acknowledge(acknowledged,confirmation);
        ManualOrderCommand child=require(user,id);
        if("NEW".equals(child.kind())) throw new ApiException(ErrorCode.VALIDATION_ERROR);
        // 소비된 요청의 재조회도 토큰 검증을 먼저 수행합니다.
        if(token==null || !MessageDigest.isEqual(hash(token).getBytes(StandardCharsets.US_ASCII),
            child.tokenHash().getBytes(StandardCharsets.US_ASCII))) throw new ApiException(ErrorCode.VALIDATION_ERROR);
        if(!"PREPARED".equals(child.status())) return ManualOrderResponse.from(child);
        ready();
        ManualOrderCommand parent=require(user,child.parentId());
        requireChangeable(parent);
        if(!binding.matches(child.accountFingerprint()) || !"OPEN".equals(sync(user,parent.commandId()).status())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"주문 상태 또는 계좌 설정이 바뀌었습니다. 다시 확인하세요.");
        }
        if("AMEND".equals(child.kind())) validateAmend(user,request(child),parent);
        return transmit(child,KbLimitOrderContract.encodeChange(request(child),child.kind(),parent.orderNo()));
    }

    public ManualOrderObservation sync(Long user,String id) {
        ManualOrderCommand c=require(user,id);
        if(!binding.matches(c.accountFingerprint())) throw new ApiException(ErrorCode.VALIDATION_ERROR,"승인 당시 계좌 설정과 다릅니다.");
        var reconciliation=mapper.reconciliation(id,user);
        String knownOrderNo=reconciliation==null?c.orderNo():reconciliation.orderNo();
        if((!"ACCEPTED".equals(c.status()) && reconciliation==null) || knownOrderNo==null) throw new ApiException(ErrorCode.VALIDATION_ERROR,
            "알려진 KB 접수 주문번호가 필요합니다. 불명확한 전송은 KB 앱과 기존 수동 대조에서 확인하세요.");
        KbOrderLookupResponse lookup=executions.findByOrderNumber(c.orderDate(),knownOrderNo);
        KbOrderExecutionItemResponse row=lookup.completeScan() && lookup.matches().size()==1?lookup.matches().get(0):null;
        boolean matches=row!=null && c.stockCode().equals(row.stockCode())
            && c.quantity().compareTo(row.orderQuantity())==0 && row.orderPrice()!=null
            && c.price().compareTo(row.orderPrice())==0
            && ("BUY".equals(c.side())?"매수":"매도").equals(row.tradeTypeName());
        String status=matches && !"CANCEL".equals(c.kind())?row.status():"UNKNOWN";
        ManualOrderObservation observation=new ManualOrderObservation(id,status,lookup.completeScan(),
            matches?row.filledQuantity():null,matches?row.openQuantity():null,LocalDateTime.now(KST));
        mapper.observe(observation);
        return observation;
    }
    public List<ManualOrderObservation> observations(Long user,String id) {
        require(user,id);return mapper.observations(id);
    }

    private ManualOrderResponse transmit(ManualOrderCommand c,KbLimitOrderContract.Request request) {
        String executionKey=UUID.randomUUID().toString();
        return OrderSubmissionWorkflow.execute(() -> store.claim(c,executionKey), () -> {
            ready();
            if(!binding.matches(c.accountFingerprint())) throw new IllegalStateException("account changed");
            dispatch.begin(c,executionKey);
            return client.sendOrderOnce(request);
        }, outcome -> {
            dispatch.recordOutcome(c,executionKey,outcome);
            dispatch.complete(c.userId(),c.commandId());
        }, () -> get(c.userId(),c.commandId()));
    }
    private void validateFresh(Long user,OrderPrecheckRequest request) {
        KbLimitOrderContract.requireSupported(request);
        if(!precheckService.precheck(user,request).eligible()) throw new ApiException(ErrorCode.VALIDATION_ERROR,"최신 주문 안전 조건을 통과하지 못했습니다.");
    }
    private void validateAmend(Long user,OrderPrecheckRequest request,ManualOrderCommand parent) {
        // 가격 증액은 예약된 자원과 신규 가용 자원의 합산이 필요하므로 현재 범위에서 차단합니다.
        if(request.limitPrice().compareTo(parent.price())>=0) throw new ApiException(ErrorCode.VALIDATION_ERROR,
            "현재는 지정가 인하만 지원합니다. 가격 증액은 KB 앱에서 확인하세요.");
        OrderPrecheckResponse check=precheckService.precheck(user,request);
        if(check.checks().stream().filter(x->!Set.of("BUYING_POWER","SELLABLE_QUANTITY").contains(x.code())).anyMatch(x->!x.passed())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"최신 시세·주문 한도 검증을 통과하지 못했습니다.");
        }
    }
    private void requireChangeable(ManualOrderCommand c) {
        OrderWorkflowRules.requireChangeable(c.kind(),c.status(),c.changeId()!=null,today().equals(c.orderDate()));
    }
    private OrderPrecheckRequest request(ManualOrderCommand c) {return new OrderPrecheckRequest(c.stockCode(),c.stockName(),c.market(),c.side(),c.price(),c.quantity());}
    private ManualOrderCommand command(Long user,Long approval,String parent,String kind,OrderPrecheckRequest r,String fingerprint,String token,String status) {
        LocalDateTime now=LocalDateTime.now(KST);
        return new ManualOrderCommand(UUID.randomUUID().toString(),user,approval,parent,kind,r.stockCode(),r.stockName(),
            r.market(),r.side(),r.limitPrice(),r.quantity(),fingerprint,token,now.plusSeconds(OrderWorkflowRules.APPROVAL_SECONDS),status,null,today(),null,null,null,now,now);
    }
    private ManualOrderCommand require(Long user,String id) {
        storage(); ManualOrderCommand c=mapper.find(id,user);
        if(c==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);return c;
    }
    private void ready() {
        if(!readiness.status().canSubmit()) throw new ApiException(ErrorCode.VALIDATION_ERROR,"실주문 스위치·공식 엔드포인트·IP/MAC·주문 저장소 준비 상태를 확인하세요.");
    }
    private void storage() {
        try {mapper.verifyStorage();}
        catch(org.springframework.dao.DataAccessException exception) {throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE);}
    }
    private void acknowledge(boolean acknowledged,String confirmation) {
        if(!acknowledged || !"실제 주문 전송".equals(confirmation)) throw new ApiException(ErrorCode.VALIDATION_ERROR,"실제 주문 전송 안내 확인이 필요합니다.");
    }
    private String today(){return LocalDate.now(KST).format(DateTimeFormatter.BASIC_ISO_DATE);}
    private String hash(String value) {
        return OrderWorkflowRules.hash(value);
    }
    public record ChangePreparation(ManualOrderResponse command,String token,LocalDateTime expiresAt) {}
}
