package com.sagopalgo.api.order.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.*;
import java.time.format.*;
import java.util.*;

/** 잔량·변경 근거를 대조하되 전송 결과/체결 완료를 추정하거나 잠금을 해제하지 않습니다. */
public final class UnknownOrderReviewRules {
    private UnknownOrderReviewRules(){}
    public static final String CONFIRMATION="잠금 유지 대조 저장";
    public static final String MESSAGE="조회 시점의 대조 관찰을 저장합니다. UNKNOWN과 전송 차단은 유지하며 주문을 다시 전송하지 않습니다. 정정·취소 구분 코드는 완료 판정으로 해석하지 않습니다.";
    public static void candidate(String status) {
        if(!"UNKNOWN".equals(status)) throw invalid("전송이 끝난 UNKNOWN만 대조합니다. SENDING은 전송 기록 진단을 사용하세요.");
    }
    public static void number(String value) {
        if(value==null || !value.matches("[0-9]{10}") || value.matches("0+")) throw invalid("확인한 숫자 10자리 주문번호를 입력하세요.");
    }
    public static Evidence verify(OrderPrecheckRequest plan,String kind,String date,LocalDateTime createdAt,String parentOrderNo,
        String orderNo,KbOrderLookupResponse lookup) {
        number(orderNo);
        if(lookup==null || !lookup.completeScan() || !date.equals(lookup.orderDate()) || !orderNo.equals(lookup.orderNo())
            || lookup.matches()==null || lookup.matches().size()!=1) throw mismatch();
        var row=lookup.matches().get(0);
        if(row==null || !orderNo.equals(row.orderNo()) || !plan.stockCode().equals(row.stockCode())
            || !("BUY".equals(plan.side())?"매수":"매도").equals(row.tradeTypeName()) || !same(plan.limitPrice(),row.orderPrice())
            || !same(plan.quantity(),row.orderQuantity()) || !positiveInteger(row.orderQuantity())
            || !nonnegativeInteger(row.filledQuantity()) || !nonnegativeInteger(row.openQuantity())
            || row.filledQuantity().compareTo(row.orderQuantity())>0 || row.openQuantity().compareTo(row.orderQuantity())>0
            || row.rejectionReason()==null || !row.rejectionReason().isBlank() || !timeMatches(date,createdAt,row.orderTime())
            || (row.correctedQuantity()!=null && !nonnegativeInteger(row.correctedQuantity()))
            || (row.sorCancelledQuantity()!=null && !nonnegativeInteger(row.sorCancelledQuantity()))) throw mismatch();
        String observation;
        String original=Objects.toString(row.originalOrderNo(),"");
        String code=Objects.toString(row.changeCode(),"");
        if(!code.isEmpty() && !code.matches("[0-9A-Za-z가-힣 _-]{1,15}")) throw mismatch();
        if("NEW".equals(kind)) {
            if(hasChangeEvidence(row) || !same(row.orderQuantity(),row.filledQuantity().add(row.openQuantity()))) throw mismatch();
            observation=row.filledQuantity().signum()==0?"OPEN":row.openQuantity().signum()==0?"FILLED":"PARTIAL";
            if(!observation.equals(row.status())) throw mismatch();
            if("FILLED".equals(observation)) throw invalid("전량 체결은 기존 KB 주문번호로 전량 체결 대조를 사용하세요.");
        } else if(Set.of("AMEND","CANCEL").contains(kind)) {
            number(parentOrderNo);
            if(orderNo.equals(parentOrderNo) || !parentOrderNo.equals(original) || code.isBlank()) throw mismatch();
            observation="CHANGE_REFERENCE";
        } else throw mismatch();
        return new Evidence(kind,observation,date,orderNo,row.orderTime(),plan.stockCode(),plan.side(),normalized(row.orderPrice()),
            normalized(row.orderQuantity()),normalized(row.filledQuantity()),normalized(row.openQuantity()),original,code,
            normalized(row.correctedQuantity()),normalized(row.sorCancelledQuantity()));
    }
    public static boolean hasChangeEvidence(KbOrderExecutionItemResponse row) {
        String original=Objects.toString(row.originalOrderNo(),"");
        return (!original.isBlank() && !original.matches("0+")) || nonzero(row.correctedQuantity()) || nonzero(row.sorCancelledQuantity());
    }
    public static String digest(Evidence evidence) {
        try {return OrderWorkflowRules.hash(new ObjectMapper().writeValueAsString(evidence));}
        catch(JsonProcessingException exception){throw new ApiException(ErrorCode.INTERNAL_ERROR);}
    }
    public static void acknowledge(boolean acknowledged,String confirmation) {
        if(!acknowledged || !CONFIRMATION.equals(confirmation)) throw invalid("원주문·조회 관찰과 잠금 유지 대조 확인이 필요합니다.");
    }
    private static boolean nonzero(BigDecimal value){return value!=null && value.signum()!=0;}
    private static boolean positiveInteger(BigDecimal value){return value!=null && value.signum()>0 && value.stripTrailingZeros().scale()<=0;}
    private static boolean nonnegativeInteger(BigDecimal value){return value!=null && value.signum()>=0 && value.stripTrailingZeros().scale()<=0;}
    private static BigDecimal normalized(BigDecimal value){return value==null?null:value.stripTrailingZeros();}
    private static boolean same(BigDecimal a,BigDecimal b){return a!=null && b!=null && a.compareTo(b)==0;}
    private static boolean timeMatches(String date,LocalDateTime createdAt,String value) {
        try {var time=LocalDate.parse(date,DateTimeFormatter.BASIC_ISO_DATE).atTime(LocalTime.parse(value,
            DateTimeFormatter.ofPattern("HHmmss").withResolverStyle(ResolverStyle.STRICT)));
            long seconds=Duration.between(createdAt,time).getSeconds();return seconds>=-2 && seconds<=300;
        } catch(DateTimeException | NullPointerException exception){return false;}
    }
    private static ApiException mismatch(){return invalid("전체 조회·단일 행·주문 항목·시각·수량 또는 원주문 연결을 대조하지 못했습니다. 차단을 유지합니다.");}
    private static ApiException invalid(String message){return new ApiException(ErrorCode.VALIDATION_ERROR,message);}
    public record Evidence(String kind,String observation,String orderDate,String orderNo,String orderTime,String stockCode,String side,
        BigDecimal price,BigDecimal quantity,BigDecimal filledQuantity,BigDecimal openQuantity,String originalOrderNo,String changeCode,
        BigDecimal correctedQuantity,BigDecimal sorCancelledQuantity){}
}
