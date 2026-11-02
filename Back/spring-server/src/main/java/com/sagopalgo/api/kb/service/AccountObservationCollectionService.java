package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.AccountObservationCollectionProperties;
import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.dto.AccountObservationCollectionResponse;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Completeness;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import com.sagopalgo.api.kb.model.AccountObservationCollectorRecord;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/** 계좌 읽기 관찰만 수집합니다. ACTIVE는 만료/추정으로 해제하지 않습니다. */
@Service
public class AccountObservationCollectionService {
    private static final Logger log=LoggerFactory.getLogger(AccountObservationCollectionService.class);
    private final AccountObservationCollectionProperties policy;
    private final PersonalModeProperties personal;
    private final SecuritiesProviderProperties providers;
    private final AccountObservationBinding binding;
    private final AccountObservationCollectorStore store;
    private final AccountObservationHistoryService history;
    private final Clock clock;
    private final AtomicBoolean running=new AtomicBoolean();

    @Autowired
    public AccountObservationCollectionService(AccountObservationCollectionProperties policy, PersonalModeProperties personal,
        SecuritiesProviderProperties providers, AccountObservationBinding binding, AccountObservationCollectorStore store,
        AccountObservationHistoryService history) {
        this(policy,personal,providers,binding,store,history,Clock.systemUTC());
    }

    AccountObservationCollectionService(AccountObservationCollectionProperties policy, PersonalModeProperties personal,
        SecuritiesProviderProperties providers, AccountObservationBinding binding, AccountObservationCollectorStore store,
        AccountObservationHistoryService history, Clock clock) {
        this.policy=policy;this.personal=personal;this.providers=providers;this.binding=binding;
        this.store=store;this.history=history;this.clock=clock;
    }

    public void collectDue() {
        if(!policy.enabled() || !personal.enabled() || personal.userId()==null || personal.userId()<=0
            || !providers.getKb().isAccountEnabled() || !running.compareAndSet(false,true)) return;
        try {
            String scope=binding.current();
            String date=LocalDate.now(clock.withZone(ZoneId.of("Asia/Seoul"))).format(DateTimeFormatter.BASIC_ISO_DATE);
            var claim=store.claim(personal.userId(),scope,UUID.randomUUID().toString(),date);
            var record=claim.record();
            if(claim.owner()) {
                finish(record,history.captureForBinding(personal.userId(),record.activeRequestId(),record.activeOrderDate(),scope));
            } else if("ACTIVE".equals(record.state())) {
                // 재시작·다중 실행은 기존 ID의 저장 결과만 읽으며 capture를 호출하지 않습니다.
                finish(record,history.detailForBinding(personal.userId(),record.activeRequestId(),scope));
            }
        } catch(ApiException exception) {
            // SQL/KB 원문·인증값·계좌 지문·예외 메시지를 로그에 복사하지 않습니다.
            log.warn("계좌 관찰 자동 수집 미확정. code={}",exception.getErrorCode().getCode());
        } catch(RuntimeException exception) {
            log.warn("계좌 관찰 자동 수집 미확정. code=COLLECTION_UNCONFIRMED");
        } finally {running.set(false);}
    }

    private void finish(AccountObservationCollectorRecord record, AccountObservationResponse result) {
        if(!record.activeRequestId().equals(result.requestId()) || !record.activeOrderDate().equals(result.orderDate())) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"수집 요청과 저장 결과가 일치하지 않습니다.");
        }
        if("PENDING".equals(result.storageState())) return;
        String failure;
        if("FAILED".equals(result.storageState())) {
            failure="CONTEXT_CHANGED".equals(result.failureCode()) ? "CONTEXT_CHANGED" : "OBSERVATION_FAILED";
        } else if(!"SUCCESS".equals(result.snapshotStatus())) {
            failure=switch(result.snapshotStatus()) {
                case "PARTIAL" -> "SNAPSHOT_PARTIAL";
                case "DISABLED" -> "SNAPSHOT_DISABLED";
                default -> "SNAPSHOT_FAILED";
            };
        } else {
            var value=result.observation();
            failure=value!=null && value.sections().stream().allMatch(s -> s.status()==Status.SUCCESS
                && s.completeness()==Completeness.COMPLETE && s.issues().isEmpty()) ? null : "SNAPSHOT_UNUSABLE";
        }
        store.finish(record.userId(),record.accountBinding(),record.activeRequestId(),record.activeOrderDate(),
            result.storageState(),result.snapshotStatus(),failure,policy.intervalSeconds());
    }

    public AccountObservationCollectionResponse status(Long user) {
        validateUser(user);
        String scope;
        try {scope=binding.current();}
        catch(ApiException exception) {
            if(exception.getErrorCode()!=ErrorCode.VALIDATION_ERROR) throw exception;
            return response(null,false);
        }
        var record=store.find(user,scope);
        assertBinding(scope);
        return response(record,true);
    }

    /** 저장된 종료 결과를 확인해 다음 주기를 허용합니다. 외부 조회나 설정 ON은 수행하지 않습니다. */
    public AccountObservationCollectionResponse resume(Long user, String lastRequestId) {
        validateUser(user);
        String request=AccountObservationInput.requestId(lastRequestId);
        String scope=binding.current();
        var record=store.find(user,scope);
        if(record==null || !"PAUSED".equals(record.state()) || !request.equals(record.lastRequestId())) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"재개 대상의 중단 기록이 일치하지 않습니다. 현재 수집 상태를 확인하세요.");
        }
        var result=history.detailForBinding(user,request,scope);
        if("PENDING".equals(result.storageState()) || !record.lastStorageState().equals(result.storageState())
            || !java.util.Objects.equals(record.lastSnapshotStatus(),result.snapshotStatus())) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"저장 결과의 종료를 확인할 수 없어 수집을 재개하지 않습니다.");
        }
        assertBinding(scope);
        store.resume(user,scope,request,policy.intervalSeconds());
        var resumed=store.find(user,scope);
        assertBinding(scope);
        return response(resumed,true);
    }

    private AccountObservationCollectionResponse response(AccountObservationCollectorRecord value, boolean configured) {
        return new AccountObservationCollectionResponse(policy.enabled(),personal.enabled(),providers.getKb().isAccountEnabled(),
            configured,policy.intervalSeconds(),!configured ? "UNCONFIGURED" : value==null ? "NOT_STARTED" : value.state(),
            value==null ? null : value.activeRequestId(),value==null ? null : value.activeOrderDate(),
            value==null ? null : value.lastRequestId(),value==null ? null : value.lastStorageState(),
            value==null ? null : value.lastSnapshotStatus(),value==null ? null : value.failureCode(),
            value==null ? null : instant(value.nextDueAt()),value==null ? null : instant(value.startedAt()),
            value==null ? null : instant(value.completedAt()),true,false);
    }
    private Instant instant(LocalDateTime value) {return value==null ? null : value.toInstant(ZoneOffset.UTC);}
    private void validateUser(Long user) {
        if(user==null || user<=0) throw new ApiException(ErrorCode.VALIDATION_ERROR,"로컬 사용자 설정이 필요합니다.");
    }
    private void assertBinding(String scope) {
        if(!binding.matches(scope)) throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"계좌 연결이 변경되었습니다. 수집 상태를 다시 조회하세요.");
    }
}
