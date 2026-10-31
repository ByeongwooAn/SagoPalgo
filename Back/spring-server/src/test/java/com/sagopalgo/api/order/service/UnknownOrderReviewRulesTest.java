package com.sagopalgo.api.order.service;
import static org.assertj.core.api.Assertions.*;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class UnknownOrderReviewRulesTest {
    final OrderPrecheckRequest plan=new OrderPrecheckRequest("005930","삼성전자","KOSPI","BUY",new BigDecimal("100.00"),new BigDecimal("2"));
    final LocalDateTime time=LocalDateTime.of(2026,11,1,9,0);
    @ParameterizedTest @ValueSource(strings={"OPEN","PARTIAL"}) void observesConsistentRemainingQuantity(String status) {
        var e=verify("NEW",row(status));assertThat(e.observation()).isEqualTo(status);
        assertThat(e.quantity()).isEqualByComparingTo(e.filledQuantity().add(e.openQuantity()));
        assertThat(UnknownOrderReviewRules.digest(e)).hasSize(64);
    }
    @ParameterizedTest @ValueSource(strings={"AMEND","CANCEL"}) void preservesOpaqueChangeCodeWithoutInferringOutcome(String kind) {
        var e=verify(kind,row(kind));assertThat(e.observation()).isEqualTo("CHANGE_REFERENCE");
        assertThat(e.originalOrderNo()).isEqualTo("0040000637");assertThat(e.changeCode()).isEqualTo("9");
    }
    @ParameterizedTest @ValueSource(strings={"stock","side","price","quantity","early","late","time","sum","fraction","negative","rejection","original","corrected","sor","status","filled"})
    void wrongOrChangedNewOrderEvidenceIsRejected(String type) {
        assertThatThrownBy(()->verify("NEW",row(type))).isInstanceOf(RuntimeException.class);
    }
    @ParameterizedTest @ValueSource(strings={"wrongParent","noCode","noParent","sameNumber"})
    void changeNeedsExactKnownParentAndExplicitChangeField(String type) {
        assertThatThrownBy(()->verify("CANCEL",row(type))).isInstanceOf(RuntimeException.class);
    }
    @Test void incompleteDuplicateAndEmptyRowsNeverPrepare() {
        for(var lookup:List.of(new KbOrderLookupResponse("20261101","0040000638",false,1,List.of(row("OPEN"))),
            new KbOrderLookupResponse("20261101","0040000638",true,1,List.of(row("OPEN"),row("OPEN"))),
            new KbOrderLookupResponse("20261101","0040000638",true,1,List.of()))) {
            assertThatThrownBy(()->UnknownOrderReviewRules.verify(plan,"NEW","20261101",time,"","0040000638",lookup)).isInstanceOf(RuntimeException.class);
        }
    }
    @Test void digestUsesNormalizedNumbersAndDetectsObservationDrift() {
        var a=verify("NEW",row("OPEN"));var b=verify("NEW",row("PARTIAL"));
        assertThat(UnknownOrderReviewRules.digest(a)).isNotEqualTo(UnknownOrderReviewRules.digest(b));
        var otherPlan=new OrderPrecheckRequest("005930","이름","KOSPI","BUY",new BigDecimal("100.000"),new BigDecimal("2.0000"));
        var other=UnknownOrderReviewRules.verify(otherPlan,"NEW","20261101",time,"","0040000638",new KbOrderLookupResponse("20261101","0040000638",true,1,List.of(row("OPEN"))));
        assertThat(UnknownOrderReviewRules.digest(a)).isEqualTo(UnknownOrderReviewRules.digest(other));
    }
    @Test void sendingAndWrongAcknowledgementCannotBeConfirmed() {
        assertThatThrownBy(()->UnknownOrderReviewRules.candidate("SENDING")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->UnknownOrderReviewRules.acknowledge(false,"잠금 유지 대조 저장")).isInstanceOf(RuntimeException.class);
        assertThatThrownBy(()->UnknownOrderReviewRules.acknowledge(true,"전량 체결 대조 확정")).isInstanceOf(RuntimeException.class);
    }
    private UnknownOrderReviewRules.Evidence verify(String kind,KbOrderExecutionItemResponse row) {
        return UnknownOrderReviewRules.verify(plan,kind,"20261101",time,"NEW".equals(kind)?"":"0040000637","0040000638",new KbOrderLookupResponse("20261101","0040000638",true,1,List.of(row)));
    }
    private KbOrderExecutionItemResponse row(String type) {
        boolean change=List.of("AMEND","CANCEL","wrongParent","noCode","noParent","sameNumber").contains(type);
        BigDecimal filled="PARTIAL".equals(type)?BigDecimal.ONE:"filled".equals(type)?new BigDecimal("2"):BigDecimal.ZERO;
        BigDecimal open="PARTIAL".equals(type)?BigDecimal.ONE:"filled".equals(type)||"CANCEL".equals(type)?BigDecimal.ZERO:new BigDecimal("2");
        return new KbOrderExecutionItemResponse("sameNumber".equals(type)?"0040000637":"0040000638","stock".equals(type)?"000660":"005930","private-name",
            "side".equals(type)?"매도":"매수",switch(type){case "early"->"085957";case "late"->"090501";case "time"->"250000";default->"090001";},
            "quantity".equals(type)?BigDecimal.ONE:new BigDecimal("2"),"negative".equals(type)?BigDecimal.ONE.negate():filled,
            "sum".equals(type)?BigDecimal.ONE:"fraction".equals(type)?new BigDecimal("0.5"):open,
            "price".equals(type)?BigDecimal.TEN:new BigDecimal("100"),null,"rejection".equals(type)?"private-reason":"",
            "PARTIAL".equals(type)?"PARTIAL":"filled".equals(type)?"FILLED":"status".equals(type)?"UNKNOWN":"OPEN",
            "wrongParent".equals(type)?"0040000611":"noParent".equals(type)?"":change||"original".equals(type)?"0040000637":"",
            change && !"noCode".equals(type)?"9":"","corrected".equals(type)?BigDecimal.ONE:BigDecimal.ZERO,
            "sor".equals(type)?BigDecimal.ONE:BigDecimal.ZERO);
    }
}
