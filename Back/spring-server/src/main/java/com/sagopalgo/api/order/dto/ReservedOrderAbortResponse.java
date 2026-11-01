package com.sagopalgo.api.order.dto;

import java.time.LocalDateTime;

/** 검증된 로컬 전송 차단 감사만 공개합니다. 실행 소유권·계좌 지문은 반환하지 않습니다. */
public record ReservedOrderAbortResponse(String source,LocalDateTime abortedAt) {
    public static ReservedOrderAbortResponse from(LocalDateTime at){return at==null?null:new ReservedOrderAbortResponse("LOCAL_BEFORE_DISPATCH",at);}
}
