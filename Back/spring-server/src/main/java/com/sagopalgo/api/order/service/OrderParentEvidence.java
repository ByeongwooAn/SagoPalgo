package com.sagopalgo.api.order.service;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.*;
import java.time.format.*;

/** 알려진 원주문 행을 추가 조회한 관찰입니다. 구분 코드나 잔량 0을 완료 근거로 승격하지 않습니다. */
public final class OrderParentEvidence {
    private OrderParentEvidence(){}
    public static Snapshot failed(String number,String verification){return new Snapshot(number,"",null,null,null,null,null,null,verification);}
    public static Snapshot inspect(OrderPrecheckRequest plan,String date,LocalDateTime createdAt,String number,KbOrderLookupResponse lookup) {
        if(lookup==null) return failed(number,"LOOKUP_FAILED");
        if(!date.equals(lookup.orderDate()) || !number.equals(lookup.orderNo())) return failed(number,"SCOPE_MISMATCH");
        if(!lookup.completeScan()) return failed(number,"INCOMPLETE");
        if(lookup.matches()==null || lookup.matches().size()!=1) return failed(number,"ROW_NOT_UNIQUE");
        var r=lookup.matches().get(0);
        if(r==null || !number.equals(r.orderNo()) || !plan.stockCode().equals(r.stockCode())
            || !("BUY".equals(plan.side())?"매수":"매도").equals(r.tradeTypeName()) || !same(plan.limitPrice(),r.orderPrice())
            || !same(plan.quantity(),r.orderQuantity()) || !timeMatches(date,createdAt,r.orderTime())
            || r.rejectionReason()==null || !r.rejectionReason().isBlank()) return failed(number,"IDENTITY_MISMATCH");
        if(!quantity(r.filledQuantity()) || !quantity(r.openQuantity()) || r.filledQuantity().add(r.openQuantity()).compareTo(plan.quantity())>0
            || (r.correctedQuantity()!=null && !quantity(r.correctedQuantity()))
            || (r.sorCancelledQuantity()!=null && !quantity(r.sorCancelledQuantity()))) return failed(number,"QUANTITY_INVALID");
        return new Snapshot(number,r.orderTime(),norm(r.orderPrice()),norm(r.orderQuantity()),norm(r.filledQuantity()),norm(r.openQuantity()),
            norm(r.correctedQuantity()),norm(r.sorCancelledQuantity()),"REFERENCE_MATCH");
    }
    private static boolean quantity(BigDecimal n){return n!=null && n.signum()>=0 && n.stripTrailingZeros().scale()<=0;}
    private static BigDecimal norm(BigDecimal n){return n==null?null:n.stripTrailingZeros();}
    private static boolean same(BigDecimal a,BigDecimal b){return a!=null && b!=null && a.compareTo(b)==0;}
    private static boolean timeMatches(String date,LocalDateTime createdAt,String value){
        try{long seconds=Duration.between(createdAt,LocalDate.parse(date,DateTimeFormatter.BASIC_ISO_DATE).atTime(LocalTime.parse(value,
            DateTimeFormatter.ofPattern("HHmmss").withResolverStyle(ResolverStyle.STRICT)))).getSeconds();return seconds>=-2 && seconds<=300;}
        catch(DateTimeException | NullPointerException exception){return false;}
    }
    public record Snapshot(String orderNo,String orderTime,BigDecimal price,BigDecimal quantity,BigDecimal filledQuantity,BigDecimal openQuantity,
        BigDecimal correctedQuantity,BigDecimal sorCancelledQuantity,String verification){}
}
