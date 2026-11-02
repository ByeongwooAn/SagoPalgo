package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.AccountObservationResponse.Page;
import com.sagopalgo.api.kb.dto.AccountObservationResponse.Summary;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.List;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/** 명시적 저장 요청만 새 KB 관찰을 실행합니다. GET/중복 POST는 저장 이력만 읽습니다. */
@Service
public class AccountObservationHistoryService {
    private final AccountObservationStore store;
    private final AccountObservationBinding binding;
    private final KbAccountSnapshotService observer;
    private final AccountObservationCodec codec;
    private final Clock clock;

    @Autowired
    public AccountObservationHistoryService(AccountObservationStore store, AccountObservationBinding binding,
        KbAccountSnapshotService observer, AccountObservationCodec codec) {
        this(store, binding, observer, codec, Clock.systemUTC());
    }

    AccountObservationHistoryService(AccountObservationStore store, AccountObservationBinding binding,
        KbAccountSnapshotService observer, AccountObservationCodec codec, Clock clock) {
        this.store = store;
        this.binding = binding;
        this.observer = observer;
        this.codec = codec;
        this.clock = clock;
    }

    public AccountObservationResponse capture(Long user, String requestId, String orderDate) {
        return captureBound(user,requestId,orderDate,null);
    }

    /** 수집 상태를 예약한 연결과 실제 관찰 연결이 달라지면 외부 조회 전에 차단합니다. */
    AccountObservationResponse captureForBinding(Long user, String requestId, String orderDate, String expectedBinding) {
        return captureBound(user,requestId,orderDate,expectedBinding);
    }

    private AccountObservationResponse captureBound(Long user, String requestId, String orderDate, String expectedBinding) {
        validateUser(user);
        String request = requestId(requestId);
        String date = orderDate(orderDate);
        String scope = binding.current();
        if(expectedBinding!=null && !expectedBinding.equals(scope)) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"수집을 예약한 계좌 연결이 변경되었습니다.");
        }
        var reservation = store.reserve(user, request, scope, date, now());
        var record = reservation.record();
        if (!scope.equals(record.accountBinding()) || !date.equals(record.orderDate())) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "요청 ID의 계좌 연결 또는 조회 일자가 다릅니다. 기존 이력을 확인하세요.");
        }
        if (!reservation.owner()) {
            assertBinding(scope);
            return response(record);
        }
        if (!binding.matches(scope)) return response(store.fail(user, request, scope, "CONTEXT_CHANGED", now()));
        KbAccountSnapshotResponse observation;
        AccountObservationCodec.Encoded encoded;
        try {
            observation = observer.observe(date);
            if (!binding.matches(scope) || contextChanged(observation)) {
                return response(store.fail(user, request, scope, "CONTEXT_CHANGED", now()));
            }
            encoded = codec.encode(observation, date);
        } catch (ApiException exception) {
            // 저장소 오류는 PENDING을 보존합니다. 같은 요청으로 관찰을 다시 실행하지 않습니다.
            if (exception.getErrorCode() == ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE) throw exception;
            return response(store.fail(user, request, scope, "OBSERVATION_FAILED", now()));
        } catch (RuntimeException exception) {
            return response(store.fail(user, request, scope, "OBSERVATION_FAILED", now()));
        }
        var completed = store.complete(user, request, scope, observation.observationId(), observation.status().name(), encoded, now());
        if (!binding.matches(scope)) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "계좌 연결이 변경되었습니다. 현재 연결의 이력을 조회하세요.");
        }
        return response(completed);
    }

    public AccountObservationResponse detail(Long user, String requestId) {
        return detailForBinding(user,requestId,null);
    }

    AccountObservationResponse detailForBinding(Long user, String requestId, String expectedBinding) {
        validateUser(user);
        String request = requestId(requestId);
        String scope = binding.current();
        if(expectedBinding!=null && !expectedBinding.equals(scope)) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"수집을 예약한 계좌 연결이 변경되었습니다.");
        }
        var record = store.find(user, scope, request);
        assertBinding(scope);
        if (record == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "현재 계좌 연결의 관찰 이력이 없습니다.");
        return response(record);
    }

    public Page history(Long user, Long beforeId, int limit) {
        validateUser(user);
        if (limit < 1 || limit > 100 || (beforeId != null && beforeId <= 0)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "이력 크기는 1~100, 이전 커서는 양수여야 합니다.");
        }
        String scope = binding.current();
        List<AccountObservationRecord> records = store.recent(user, scope, beforeId, limit + 1);
        assertBinding(scope);
        var visible = records.subList(0, Math.min(limit, records.size()));
        Long next = records.size() > limit ? visible.get(visible.size() - 1).id() : null;
        return new Page(visible.stream().map(this::summary).toList(), next);
    }

    private boolean contextChanged(KbAccountSnapshotResponse observation) {
        return observation != null && observation.sections() != null && observation.sections().stream()
            .filter(s -> s != null && s.issues() != null).flatMap(s -> s.issues().stream())
            .anyMatch(i -> i != null && "CONTEXT_CHANGED".equals(i.code()));
    }

    private void assertBinding(String scope) {
        if (!binding.matches(scope)) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "계좌 연결이 변경되었습니다. 현재 연결의 이력을 다시 조회하세요.");
        }
    }

    private AccountObservationResponse response(AccountObservationRecord r) {
        return new AccountObservationResponse(r.requestId(), r.orderDate(), r.storageState(), r.observationId(),
            r.snapshotStatus(), instant(r.createdAt()), instant(r.completedAt()), r.failureCode(), true, codec.decode(r));
    }

    private Summary summary(AccountObservationRecord r) {
        return new Summary(r.requestId(), r.orderDate(), r.storageState(), r.observationId(), r.snapshotStatus(),
            instant(r.createdAt()), instant(r.completedAt()), r.failureCode(), true);
    }

    private Instant instant(LocalDateTime value) { return value == null ? null : value.toInstant(ZoneOffset.UTC); }
    private LocalDateTime now() { return LocalDateTime.ofInstant(clock.instant().truncatedTo(ChronoUnit.MICROS), ZoneOffset.UTC); }

    private void validateUser(Long user) {
        if (user == null || user <= 0) throw new ApiException(ErrorCode.VALIDATION_ERROR, "로컬 사용자 설정이 필요합니다.");
    }

    private String requestId(String value) {
        return AccountObservationInput.requestId(value);
    }

    private String orderDate(String value) {
        try {
            if (value == null || !value.matches("[0-9]{8}")) throw new IllegalArgumentException();
            LocalDate.parse(value, DateTimeFormatter.BASIC_ISO_DATE);
            return value;
        } catch (RuntimeException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "관찰 주문일은 YYYYMMDD의 실제 날짜여야 합니다.");
        }
    }
}
