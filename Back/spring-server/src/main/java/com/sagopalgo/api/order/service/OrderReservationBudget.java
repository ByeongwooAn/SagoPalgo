package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import java.math.BigDecimal;
import java.util.Set;

/** 증권사 예약금의 존재를 증명하지 않는 순수 계산입니다. 호출자가 소유권·가용 잔량을 입증해야 합니다. */
public final class OrderReservationBudget {
    private OrderReservationBudget() {}
    public static Budget calculate(String side,String kind,BigDecimal oldPrice,BigDecimal newPrice,
        BigDecimal selected,BigDecimal remaining) {
        if(!Set.of("BUY","SELL").contains(side) || !Set.of("AMEND","CANCEL").contains(kind)
            || !whole(selected) || selected.signum()<=0 || !whole(remaining) || selected.compareTo(remaining)>0
            || oldPrice==null || oldPrice.signum()<=0 || newPrice==null || newPrice.signum()<=0) throw invalid();
        if("AMEND".equals(kind)) OrderWorkflowRules.requireAmendedPrice(oldPrice,newPrice);
        BigDecimal original="BUY".equals(side)?oldPrice.multiply(selected):BigDecimal.ZERO;
        BigDecimal changed="BUY".equals(side) && "AMEND".equals(kind)?newPrice.multiply(selected):BigDecimal.ZERO;
        return new Budget(n(selected),n(remaining),n(original),n(changed),n(changed.subtract(original).max(BigDecimal.ZERO)),
            n(original.subtract(changed).max(BigDecimal.ZERO)),selected.compareTo(remaining)==0?"ALL":"PARTIAL");
    }
    public static boolean whole(BigDecimal value){return value!=null && value.signum()>=0 && value.stripTrailingZeros().scale()<=0;}
    private static BigDecimal n(BigDecimal value){return value.stripTrailingZeros();}
    private static ApiException invalid(){return new ApiException(ErrorCode.VALIDATION_ERROR,"변경 수량은 현재 미체결 잔량 이내의 양수 정수여야 합니다.");}
    public record Budget(BigDecimal selectedQuantity,BigDecimal remainingQuantity,BigDecimal reusedCash,BigDecimal newReservedCash,
        BigDecimal additionalCash,BigDecimal releasedCash,String scope) {}
}
