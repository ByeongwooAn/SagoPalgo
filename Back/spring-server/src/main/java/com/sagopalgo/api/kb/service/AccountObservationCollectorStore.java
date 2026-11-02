package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.mapper.AccountObservationCollectorMapper;
import com.sagopalgo.api.kb.model.AccountObservationCollectorRecord;
import java.util.function.Supplier;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class AccountObservationCollectorStore {
    private final AccountObservationCollectorMapper mapper;
    private final TransactionTemplate transaction;

    public AccountObservationCollectorStore(AccountObservationCollectorMapper mapper, PlatformTransactionManager manager) {
        this.mapper=mapper;
        transaction=new TransactionTemplate(manager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public record Claim(AccountObservationCollectorRecord record, boolean owner) {}

    public Claim claim(Long user, String binding, String request, String date) {
        return call(() -> transaction.execute(tx -> {
            mapper.initialize(user,binding);
            boolean owner=mapper.claim(user,binding,request,date)==1;
            var record=mapper.find(user,binding);
            if(record==null) throw unavailable();
            return new Claim(record,owner);
        }));
    }

    public AccountObservationCollectorRecord find(Long user, String binding) {
        return call(() -> mapper.find(user,binding));
    }

    public void finish(Long user, String binding, String request, String date, String storage, String snapshot,
        String failure, int interval) {
        // 다른 프로세스가 같은 완료 기록을 먼저 대조한 경우 조건부 UPDATE는 0이며 재실행하지 않습니다.
        call(() -> transaction.execute(tx -> mapper.finish(user,binding,request,date,
            failure==null ? "IDLE" : "PAUSED",storage,snapshot,failure,interval)));
    }

    public void resume(Long user, String binding, String lastRequest, int interval) {
        call(() -> transaction.execute(tx -> {
            if(mapper.resume(user,binding,lastRequest,interval)!=1) {
                throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"수집 상태가 변경됐습니다. 현재 상태를 다시 확인하세요.");
            }
            return null;
        }));
    }

    private <T> T call(Supplier<T> work) {
        try {return work.get();}
        catch(DataAccessException exception) {throw unavailable();}
    }
    private ApiException unavailable() {return new ApiException(ErrorCode.OBSERVATION_COLLECTION_STORAGE_UNAVAILABLE);}
}
