package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.*;
import java.time.format.*;
import java.util.*;

/** 조회 관찰만 분류합니다. 일치해도 전송 종료·원주문 연결·잠금 해제 근거로 사용하지 않습니다. */
public final class OrderSendingDiagnosticRules {
    private OrderSendingDiagnosticRules() {}
    public static final String MESSAGE="진단 시점의 관찰만 저장했습니다. 항목 일치나 빈 결과는 전송 종료·원주문 연결의 증거가 아닙니다. 주문 상태와 잠금은 변경하지 않습니다.";
    public static void validate(String id,String orderNo,boolean acknowledged,String confirmation) {
        if(id==null || !id.matches("[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
            || orderNo==null || !orderNo.matches("[0-9]{10}") || orderNo.matches("0+")
            || !acknowledged || !"잠금 유지 진단".equals(confirmation)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"확인한 숫자 10자리 주문번호와 잠금 유지 진단 확인이 필요합니다.");
        }
    }
    public static void requireCandidate(String status,String phase) {
        if(!"SENDING".equals(status) || "RETURNED".equals(phase)) throw new ApiException(ErrorCode.VALIDATION_ERROR,
            "종료 결과 없는 SENDING만 진단합니다. 저장된 전송 기록을 새로고침하세요.");
    }
    public static Report failure(String assessment) {
        return new Report(assessment,List.of(),null,false,0,"","",MESSAGE);
    }
    public static Report evaluate(OrderPrecheckRequest plan,String kind,String date,LocalDateTime createdAt,
        String orderNo,KbOrderLookupResponse lookup) {
        if(lookup==null) return failure("LOOKUP_FAILED");
        var checks=new ArrayList<Check>();
        boolean envelope=Objects.equals(date,lookup.orderDate()) && Objects.equals(orderNo,lookup.orderNo());
        checks.add(new Check("REQUEST_SCOPE",envelope));
        checks.add(new Check("COMPLETE_SCAN",lookup.completeScan()));
        var rows=lookup.matches()==null?List.<KbOrderExecutionItemResponse>of():lookup.matches();
        checks.add(new Check("SINGLE_ROW",rows.size()==1));
        String assessment;
        Observation observation=null;
        if(!envelope) assessment="MISMATCH";
        else if(!lookup.completeScan()) assessment="INCOMPLETE";
        else if(rows.isEmpty()) assessment="NOT_FOUND";
        else if(rows.size()!=1 || rows.get(0)==null) assessment="AMBIGUOUS";
        else {
            var row=rows.get(0);
            checks.add(new Check("NEW_ORDER", "NEW".equals(kind)));
            checks.add(new Check("ORDER_NUMBER",orderNo.equals(row.orderNo())));
            checks.add(new Check("STOCK_CODE",Objects.equals(plan.stockCode(),row.stockCode())));
            checks.add(new Check("SIDE",("BUY".equals(plan.side())?"매수":"매도").equals(row.tradeTypeName())));
            checks.add(new Check("PRICE",same(plan.limitPrice(),row.orderPrice())));
            checks.add(new Check("QUANTITY",same(plan.quantity(),row.orderQuantity())));
            checks.add(new Check("TIME_WINDOW",timeMatches(date,createdAt,row.orderTime())));
            boolean quantities=row.orderQuantity()!=null && row.filledQuantity()!=null && row.openQuantity()!=null
                && row.orderQuantity().signum()>0 && row.filledQuantity().signum()>=0 && row.openQuantity().signum()>=0
                && same(row.orderQuantity(),row.filledQuantity().add(row.openQuantity()));
            checks.add(new Check("QUANTITY_CONSISTENCY",quantities));
            checks.add(new Check("NO_REJECTION",row.rejectionReason()!=null && row.rejectionReason().isBlank()));
            // 원문 종목명/거절 사유/메시지는 보관하지 않습니다. 검증된 숫자와 고정 코드만 투영합니다.
            observation=new Observation(safe(row.orderNo(),"[0-9]{10}"),safe(row.stockCode(),"[0-9]{6}"),
                safe(row.orderTime(),"[0-9]{6}"),row.orderPrice(),row.orderQuantity(),row.filledQuantity(),row.openQuantity(),
                List.of("OPEN","PARTIAL","FILLED").contains(Objects.toString(row.status(),""))?row.status():"UNKNOWN",
                row.rejectionReason()==null || !row.rejectionReason().isBlank());
            assessment=!"NEW".equals(kind)?"CHANGE_REQUIRES_REVIEW":checks.stream().allMatch(Check::passed)?"FIELDS_MATCH":"MISMATCH";
        }
        return new Report(assessment,List.copyOf(checks),observation,lookup.completeScan(),lookup.pagesScanned(),"","",MESSAGE);
    }
    private static boolean same(BigDecimal a,BigDecimal b){return a!=null && b!=null && a.compareTo(b)==0;}
    private static String safe(String value,String pattern){return value!=null && value.matches(pattern)?value:"";}
    private static boolean timeMatches(String date,LocalDateTime createdAt,String value) {
        try {
            var formatter=DateTimeFormatter.ofPattern("HHmmss").withResolverStyle(ResolverStyle.STRICT);
            var time=LocalDate.parse(date,DateTimeFormatter.BASIC_ISO_DATE).atTime(LocalTime.parse(value,formatter));
            long seconds=Duration.between(createdAt,time).getSeconds();
            return seconds>=-2 && seconds<=300;
        } catch(DateTimeException | NullPointerException exception){return false;}
    }
    public record Check(String code,boolean passed){}
    public record Observation(String orderNo,String stockCode,String orderTime,BigDecimal price,BigDecimal quantity,
        BigDecimal filledQuantity,BigDecimal openQuantity,String status,boolean rejectionPresent){}
    public record Report(String assessment,List<Check> checks,Observation observation,boolean completeScan,int pagesScanned,
        String phaseAfter,String commandStatusAfter,String message) {
        public Report after(String phase,String status,boolean accountMatches) {
            var source=accountMatches?this:failure("ACCOUNT_CHANGED");
            return new Report(source.assessment,source.checks,source.observation,source.completeScan,source.pagesScanned,phase,status,MESSAGE);
        }
    }
}
