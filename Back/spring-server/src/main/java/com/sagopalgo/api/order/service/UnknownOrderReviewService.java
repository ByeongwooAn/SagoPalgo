package com.sagopalgo.api.order.service;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.mapper.UnknownOrderReviewMapper.*;
import com.sagopalgo.api.order.model.ManualOrderCommand;
import java.time.LocalDateTime;
import java.util.*;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
@Service
public class UnknownOrderReviewService {
    private final ManualOrderMapper commands;
    private final UnknownOrderReviewMapper reviews;
    private final UnknownOrderReviewStore store;
    private final OrderAccountBinding binding;
    private final KbOrderExecutionService executions;
    private final ObjectMapper json;
    public UnknownOrderReviewService(ManualOrderMapper commands,UnknownOrderReviewMapper reviews,UnknownOrderReviewStore store,
        OrderAccountBinding binding,KbOrderExecutionService executions,ObjectMapper json){this.commands=commands;this.reviews=reviews;this.store=store;this.binding=binding;this.executions=executions;this.json=json;}
    public Preparation prepare(Long user,String id,String orderNo) {
        storage();UnknownOrderReviewRules.number(orderNo);var c=candidate(user,id);
        var evidence=verify(c,orderNo);String token=OrderWorkflowRules.issueToken();var now=UnknownOrderReviewStore.now();
        var row=new PreparationRow(id,user,UUID.randomUUID().toString(),c.accountFingerprint(),OrderWorkflowRules.hash(token),
            UnknownOrderReviewRules.digest(evidence),encode(evidence),now.plusSeconds(90),now);
        try{store.prepare(row);}catch(DataAccessException exception){throw unavailable();}
        return new Preparation(row.reviewId(),token,row.expiresAt(),evidence,UnknownOrderReviewRules.MESSAGE);
    }
    public Response confirm(Long user,String id,String reviewId,String token,boolean acknowledged,String confirmation) {
        UnknownOrderReviewRules.acknowledge(acknowledged,confirmation);
        if(token==null || token.length()>200 || reviewId==null || reviewId.length()!=36) throw invalid();
        storage();var owned=commands.find(id,user);if(owned==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        String hash=OrderWorkflowRules.hash(token);
        var previous=reviews.find(reviewId,user,id);
        if(previous!=null){if(!UnknownOrderReviewStore.sameToken(previous.tokenHash(),hash)) throw invalid();return response(previous);}
        var c=candidate(user,id);var prepared=reviews.preparation(id,user);var now=UnknownOrderReviewStore.now();
        if(prepared==null || !reviewId.equals(prepared.reviewId()) || !prepared.expiresAt().isAfter(now)
            || !UnknownOrderReviewStore.sameToken(prepared.tokenHash(),hash) || !binding.matches(prepared.accountFingerprint())) throw invalid();
        var evidence=verify(c,decode(prepared.evidenceJson()).orderNo());
        String evidenceHash=UnknownOrderReviewRules.digest(evidence);
        if(!evidenceHash.equals(prepared.evidenceHash())) throw new ApiException(ErrorCode.VALIDATION_ERROR,"체결·잔량 또는 변경 근거가 달라졌습니다. 새 조회로 다시 준비하세요. 차단은 유지됩니다.");
        var fresh=new PreparationRow(id,user,reviewId,c.accountFingerprint(),hash,evidenceHash,encode(evidence),prepared.expiresAt(),UnknownOrderReviewStore.now());
        try{return response(store.confirm(fresh));}catch(DataAccessException exception){throw unavailable();}
    }
    public List<Response> history(Long user,String id) {
        storage();if(commands.find(id,user)==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        try{return reviews.recent(id,user).stream().map(this::response).toList();}catch(DataAccessException exception){throw unavailable();}
    }
    private ManualOrderCommand candidate(Long user,String id) {
        var c=commands.find(id,user);if(c==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        UnknownOrderReviewRules.candidate(c.status());
        if(!binding.matches(c.accountFingerprint()) || commands.reconciliation(id,user)!=null) throw invalid();
        UnknownOrderReviewStore.requireParent(commands,c);return c;
    }
    private UnknownOrderReviewRules.Evidence verify(ManualOrderCommand c,String orderNo) {
        String parent=UnknownOrderReviewStore.requireParent(commands,c);
        var lookup=executions.findByOrderNumber(c.orderDate(),orderNo);
        if(!binding.matches(c.accountFingerprint())) throw invalid();
        return UnknownOrderReviewRules.verify(new OrderPrecheckRequest(c.stockCode(),c.stockName(),c.market(),c.side(),c.price(),c.quantity()),
            c.kind(),c.orderDate(),c.createdAt(),parent,orderNo,lookup);
    }
    private void storage() {
        try{commands.verifyStorage();}catch(DataAccessException exception){throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE);}
        try{reviews.verifyStorage();}catch(DataAccessException exception){throw unavailable();}
    }
    private String encode(UnknownOrderReviewRules.Evidence evidence){try{return json.writeValueAsString(evidence);}catch(JsonProcessingException exception){throw unavailable();}}
    private UnknownOrderReviewRules.Evidence decode(String value){try{return json.readValue(value,UnknownOrderReviewRules.Evidence.class);}catch(JsonProcessingException exception){throw unavailable();}}
    private Response response(ReviewRow row){return new Response(row.reviewId(),row.commandId(),decode(row.evidenceJson()),row.confirmedAt(),true,UnknownOrderReviewRules.MESSAGE);}
    private static ApiException invalid(){return new ApiException(ErrorCode.VALIDATION_ERROR,"대조 확인이 만료·변경되었거나 계좌 조건이 맞지 않습니다. 다시 준비하세요.");}
    private static ApiException unavailable(){return new ApiException(ErrorCode.REVIEW_STORAGE_UNAVAILABLE);}
    public record Preparation(String reviewId,String token,LocalDateTime expiresAt,UnknownOrderReviewRules.Evidence evidence,String message){}
    public record Response(String reviewId,String commandId,UnknownOrderReviewRules.Evidence evidence,LocalDateTime confirmedAt,boolean lockMaintained,String message){}
}
