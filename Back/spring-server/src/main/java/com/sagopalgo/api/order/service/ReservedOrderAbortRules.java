package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.model.*;
import java.util.Objects;

/** 시간 경과가 아니라 미시작 기록과 원자적 전송 차단으로만 처리합니다. */
public final class ReservedOrderAbortRules {
    public static final String CONFIRMATION="전송 전 예약 중단";
    private ReservedOrderAbortRules() {}
    public static void acknowledge(boolean checked,String text){
        if(!checked || !CONFIRMATION.equals(text)) throw new ApiException(ErrorCode.VALIDATION_ERROR,"전송 시작 전 예약을 중단한다는 별도 확인이 필요합니다.");
    }
    public static boolean candidate(ManualOrderCommand c,ManualOrderDispatchRecord d){
        return c!=null && d!=null && "SENDING".equals(c.status()) && c.orderNo()==null && "RESERVED".equals(d.phase())
            && Objects.equals(c.commandId(),d.commandId()) && Objects.equals(c.userId(),d.userId())
            && d.executionKey()!=null && !d.executionKey().isBlank() && d.reservedAt()!=null
            && d.startedAt()==null && d.returnedAt()==null && d.outcomeStatus()==null && d.orderNo()==null
            && d.resultCode()==null && d.processCode()==null;
    }
}
