package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.mapper.AccountObservationMapper;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.time.LocalDateTime;
import java.util.List;
import java.util.function.Supplier;
import org.springframework.dao.DataAccessException;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** 조회 전 예약 커밋 / 조회 후 결과 커밋. 외부 조회 중 DB 트랜잭션·잠금을 유지하지 않습니다. */
@Service
public class AccountObservationStore {
    private final AccountObservationMapper mapper;
    private final TransactionTemplate transaction;

    public AccountObservationStore(AccountObservationMapper mapper, PlatformTransactionManager manager) {
        this.mapper = mapper;
        transaction = new TransactionTemplate(manager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public record Reservation(AccountObservationRecord record, boolean owner) {}

    public Reservation reserve(Long user, String request, String binding, String date, LocalDateTime now) {
        try {
            var inserted = transaction.execute(status -> {
                if (mapper.reserve(user, request, binding, date, now) != 1) throw unavailable();
                return mapper.findRequest(user, request);
            });
            if (inserted == null) throw unavailable();
            return new Reservation(inserted, true);
        } catch (DuplicateKeyException exception) {
            // 중복 INSERT의 트랜잭션을 롤백한 뒤 읽어 RR 스냅샷/rollback-only 상태를 피합니다.
            var existing = call(() -> transaction.execute(status -> mapper.findRequest(user, request)));
            if (existing == null) throw unavailable();
            return new Reservation(existing, false);
        } catch (DataAccessException exception) { throw unavailable(); }
    }

    public AccountObservationRecord complete(Long user, String request, String binding, String observation,
        String status, AccountObservationCodec.Encoded encoded, LocalDateTime now) {
        return call(() -> transaction.execute(tx -> {
            if (mapper.complete(user, request, binding, observation, status, encoded.payload(), encoded.sha256(), now) != 1) {
                throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "이미 종료된 관찰 요청입니다. 저장 이력을 조회하세요.");
            }
            return require(mapper.findScoped(user, binding, request));
        }));
    }

    public AccountObservationRecord fail(Long user, String request, String binding, String code, LocalDateTime now) {
        return call(() -> transaction.execute(tx -> {
            if (mapper.fail(user, request, binding, code, now) != 1) throw unavailable();
            return require(mapper.findScoped(user, binding, request));
        }));
    }

    public AccountObservationRecord find(Long user, String binding, String request) {
        return call(() -> mapper.findScoped(user, binding, request));
    }

    public List<AccountObservationRecord> recent(Long user, String binding, Long before, int limit) {
        return call(() -> mapper.recent(user, binding, before, limit));
    }

    private AccountObservationRecord require(AccountObservationRecord record) {
        if (record == null) throw unavailable();
        return record;
    }

    private <T> T call(Supplier<T> task) {
        try { return task.get(); }
        catch (DataAccessException exception) { throw unavailable(); }
    }

    private ApiException unavailable() { return new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE); }
}
