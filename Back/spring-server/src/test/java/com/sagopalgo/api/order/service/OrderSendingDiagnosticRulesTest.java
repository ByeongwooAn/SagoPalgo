package com.sagopalgo.api.order.service;
import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class OrderSendingDiagnosticRulesTest {
    final LocalDateTime created=LocalDateTime.of(2026,10,31,9,0,0);
    final OrderPrecheckRequest plan=new OrderPrecheckRequest("005930","삼성전자","KOSPI","BUY",new BigDecimal("75000"),new BigDecimal("2"));
    @ParameterizedTest @ValueSource(strings={"valid","stock","side","price","quantity","time","late","number","inconsistent","rejection","missing","bad-time"})
    void checksAllReferenceFieldsAndQuantityConsistency(String variant) {
        var row=row(variant);var lookup=new KbOrderLookupResponse("20261031","0040000638",true,1,List.of(row));
        var report=OrderSendingDiagnosticRules.evaluate(plan,"NEW","20261031",created,"0040000638",lookup);
        assertThat(report.assessment()).isEqualTo("valid".equals(variant)?"FIELDS_MATCH":"MISMATCH");
        assertThat(report.toString()).doesNotContain("private-name","private-reason");
        assertThat(report.message()).contains("주문 상태와 잠금은 변경하지 않습니다");
    }
    @ParameterizedTest @ValueSource(strings={"EMPTY","DUPLICATE","INCOMPLETE","WRONG_DATE","WRONG_NUMBER","FAILURE"})
    void emptyIncompleteDuplicateAndFailedLookupCannotBecomeMatch(String type) {
        var rows="EMPTY".equals(type)?List.<KbOrderExecutionItemResponse>of():"DUPLICATE".equals(type)?List.of(row("valid"),row("valid")):List.of(row("valid"));
        var lookup="FAILURE".equals(type)?null:new KbOrderLookupResponse("WRONG_DATE".equals(type)?"20261030":"20261031",
            "WRONG_NUMBER".equals(type)?"0040000639":"0040000638",!"INCOMPLETE".equals(type),1,rows);
        var report=OrderSendingDiagnosticRules.evaluate(plan,"NEW","20261031",created,"0040000638",lookup);
        String expected=switch(type){case "EMPTY"->"NOT_FOUND";case "DUPLICATE"->"AMBIGUOUS";case "INCOMPLETE"->"INCOMPLETE";case "FAILURE"->"LOOKUP_FAILED";default->"MISMATCH";};
        assertThat(report.assessment()).isEqualTo(expected);assertThat(report.observation()).isNull();
    }
    @ParameterizedTest @ValueSource(strings={"AMEND","CANCEL"})
    void matchingChangeOrderIsObservationOnlyAndRequiresSeparateReview(String kind) {
        var report=OrderSendingDiagnosticRules.evaluate(plan,kind,"20261031",created,"0040000638",new KbOrderLookupResponse("20261031","0040000638",true,1,List.of(row("valid"))));
        assertThat(report.assessment()).isEqualTo("CHANGE_REQUIRES_REVIEW");
        assertThat(report.checks()).contains(new OrderSendingDiagnosticRules.Check("NEW_ORDER",false));
    }
    @Test void validatesAcknowledgementNumberAndDiagnosticIdBeforeAnyAction() {
        String id=UUID.randomUUID().toString();OrderSendingDiagnosticRules.validate(id,"0040000638",true,"잠금 유지 진단");
        for(String number:new String[]{"0000000000","123","account"}) assertThatThrownBy(()->OrderSendingDiagnosticRules.validate(id,number,true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->OrderSendingDiagnosticRules.validate("invalid","0040000638",true,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->OrderSendingDiagnosticRules.validate(id,"0040000638",false,"잠금 유지 진단")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->OrderSendingDiagnosticRules.validate(id,"0040000638",true,"실제 주문 전송")).isInstanceOf(RuntimeException.class);
    }
    private KbOrderExecutionItemResponse row(String variant) {
        return new KbOrderExecutionItemResponse("number".equals(variant)?"0040000639":"0040000638","stock".equals(variant)?"000660":"005930","private-name",
            "side".equals(variant)?"매도":"매수",switch(variant){case "time"->"085957";case "late"->"090501";case "bad-time"->"246001";default->"090000";},
            "quantity".equals(variant)?BigDecimal.ONE:new BigDecimal("2"),new BigDecimal("2"),"inconsistent".equals(variant)?BigDecimal.ONE:BigDecimal.ZERO,
            "missing".equals(variant)?null:"price".equals(variant)?BigDecimal.TEN:new BigDecimal("75000"),null,"rejection".equals(variant)?"private-reason":"","FILLED");
    }
}
