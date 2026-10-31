package com.sagopalgo.api.order.dto;

import java.math.BigDecimal;

/** KB 주문 조회의 원시 체결 수량을 보존하며 취소·정정 여부를 추정하지 않습니다. */
public record KbOrderExecutionItemResponse(
    String orderNo,
    String stockCode,
    String stockName,
    String tradeTypeName,
    String orderTime,
    BigDecimal orderQuantity,
    BigDecimal filledQuantity,
    BigDecimal openQuantity,
    BigDecimal orderPrice,
    BigDecimal fillPrice,
    String rejectionReason,
    String status,
    String originalOrderNo,
    String changeCode,
    BigDecimal correctedQuantity,
    BigDecimal sorCancelledQuantity
) {
    public KbOrderExecutionItemResponse(String orderNo,String stockCode,String stockName,String tradeTypeName,String orderTime,
        BigDecimal orderQuantity,BigDecimal filledQuantity,BigDecimal openQuantity,BigDecimal orderPrice,BigDecimal fillPrice,
        String rejectionReason,String status) {
        this(orderNo,stockCode,stockName,tradeTypeName,orderTime,orderQuantity,filledQuantity,openQuantity,orderPrice,fillPrice,
            rejectionReason,status,"","",null,null);
    }
}
