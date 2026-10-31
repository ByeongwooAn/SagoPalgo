package com.sagopalgo.api.order.service;
import static org.assertj.core.api.Assertions.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.order.dto.*;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
class OrderParentEvidenceTest {
    final OrderPrecheckRequest plan=new OrderPrecheckRequest("005930","삼성전자","KOSPI","BUY",new BigDecimal("100"),new BigDecimal("2"));
    final LocalDateTime time=LocalDateTime.of(2026,11,1,9,0);
    @Test void changedParentZeroRemainderIsOnlyReferenceAndContainsNoRawPrivateText() {
        var snapshot=inspect("valid");assertThat(snapshot.verification()).isEqualTo("REFERENCE_MATCH");
        assertThat(snapshot.correctedQuantity()).isEqualByComparingTo("2");assertThat(snapshot.toString()).doesNotContain("private-name","private-reason");
    }
    @ParameterizedTest @ValueSource(strings={"date","number","incomplete","empty","duplicate","stock","side","price","quantity","time","negative","over","rejection"})
    void failedParentChecksDoNotExposeUnverifiedRow(String type) {
        var result=inspect(type);assertThat(result.verification()).isNotEqualTo("REFERENCE_MATCH");assertThat(result.quantity()).isNull();
    }
    @Test void legacyEvidenceJsonStillReadsWithoutParentObservation() throws Exception {
        var json=new ObjectMapper();var row=new UnknownOrderReviewRules.Evidence("CANCEL","CHANGE_REFERENCE","20261101","0040000639","090001","005930","BUY",
            new BigDecimal("100"),new BigDecimal("2"),BigDecimal.ZERO,BigDecimal.ZERO,"0040000638","9",BigDecimal.ZERO,BigDecimal.ZERO);
        var node=json.valueToTree(row);((com.fasterxml.jackson.databind.node.ObjectNode)node).remove("parentObservation");
        assertThat(json.treeToValue(node,UnknownOrderReviewRules.Evidence.class).parentObservation()).isNull();
        assertThat(UnknownOrderReviewRules.digest(row)).isNotEqualTo(UnknownOrderReviewRules.digest(row.withParent(inspect("valid"))));
    }
    private OrderParentEvidence.Snapshot inspect(String type) {
        var row=new KbOrderExecutionItemResponse("0040000638","stock".equals(type)?"000660":"005930","private-name","side".equals(type)?"매도":"매수",
            "time".equals(type)?"100000":"090001","quantity".equals(type)?BigDecimal.ONE:new BigDecimal("2"),"negative".equals(type)?BigDecimal.ONE.negate():BigDecimal.ZERO,
            "over".equals(type)?new BigDecimal("3"):BigDecimal.ZERO,"price".equals(type)?BigDecimal.TEN:new BigDecimal("100"),null,"rejection".equals(type)?"private-reason":"","UNKNOWN","","9",new BigDecimal("2"),BigDecimal.ZERO);
        var rows="empty".equals(type)?List.<KbOrderExecutionItemResponse>of():"duplicate".equals(type)?List.of(row,row):List.of(row);
        return OrderParentEvidence.inspect(plan,"20261101",time,"0040000638",new KbOrderLookupResponse("date".equals(type)?"20261102":"20261101",
            "number".equals(type)?"0040000639":"0040000638",!"incomplete".equals(type),1,rows));
    }
}
