package com.sagopalgo.api.order.service;

import com.sagopalgo.api.order.client.KbLimitOrderContract;
import java.util.function.Consumer;
import java.util.function.Supplier;

/** 예약 커밋 → 한 번 전송 → 결과 저장. 예약/결과 저장 실패는 전송 재시도나 예약 해제로 바꾸지 않습니다. */
public final class OrderSubmissionWorkflow {
    private OrderSubmissionWorkflow() {}

    public static <T> T execute(Runnable claim, Supplier<KbLimitOrderContract.Outcome> gateway,
        Consumer<KbLimitOrderContract.Outcome> persist, Supplier<T> read) {
        claim.run();
        KbLimitOrderContract.Outcome outcome;
        try { outcome = gateway.get(); }
        catch (RuntimeException exception) {
            outcome = new KbLimitOrderContract.Outcome(KbLimitOrderContract.Status.UNKNOWN, "", "", "", "");
        }
        persist.accept(outcome);
        return read.get();
    }
}
