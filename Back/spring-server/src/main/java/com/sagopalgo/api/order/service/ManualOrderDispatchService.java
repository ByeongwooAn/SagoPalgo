package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import com.sagopalgo.api.order.dto.ReservedOrderAbortResponse;
import java.time.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 외부 HTTP와 별도인 단계/반환 결과 기록. 복구는 저장 결과만 적용하며 전송·취소·가드 해제를 하지 않습니다. */
@Service
public class ManualOrderDispatchService {
    private final ManualOrderMapper commands;
    private final ManualOrderDispatchMapper journal;
    private final OrderAccountBinding binding;

    public ManualOrderDispatchService(ManualOrderMapper commands, ManualOrderDispatchMapper journal, OrderAccountBinding binding) {
        this.commands = commands; this.journal = journal; this.binding = binding;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void begin(ManualOrderCommand command, String executionKey) {
        if (journal.begin(command.commandId(),command.userId(),executionKey,now()) != 1) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"전송 시작 기록을 확보하지 못했습니다. 다시 전송하지 않습니다.");
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recordOutcome(ManualOrderCommand command, String executionKey, KbLimitOrderContract.Outcome outcome) {
        var receipt = OrderDispatchReceipt.from(outcome);
        if (journal.returned(command.commandId(),command.userId(),executionKey,receipt.status(),receipt.orderNo(),
            receipt.resultCode(),receipt.processCode(),now()) != 1) {
            var previous = journal.find(command.commandId(),command.userId());
            if(previous!=null && executionKey.equals(previous.executionKey()) && "ABORTED".equals(previous.phase())
                && commands.abortedAt(command.commandId(),command.userId())!=null) return;
            if (previous == null || !executionKey.equals(previous.executionKey()) || !receipt.equals(previous.receipt())) {
                throw new ApiException(ErrorCode.INTERNAL_ERROR,"전송 결과 기록을 저장하지 못했습니다. 재전송 없이 기록을 확인하세요.");
            }
        }
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void complete(Long userId, String commandId) { apply(userId,commandId,false); }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void recover(Long userId, String commandId, boolean acknowledged, String confirmation) {
        if (!acknowledged || !"저장된 전송 결과 복구".equals(confirmation)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"추가 전송 없는 기록 복구임을 확인하세요.");
        }
        apply(userId,commandId,true);
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void abortReserved(Long userId,String commandId,boolean acknowledged,String confirmation) {
        ReservedOrderAbortRules.acknowledge(acknowledged,confirmation);
        if(commands.lockUser(userId)==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        var c=commands.lockCommand(commandId,userId);
        if(c==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        if(!binding.matches(c.accountFingerprint())) throw new ApiException(ErrorCode.VALIDATION_ERROR,"승인 당시 계좌 설정과 다릅니다.");
        var d=journal.lock(commandId,userId);
        // 첫 일반 조회는 잠금 획득 뒤 수행해 동시 중단의 커밋보다 오래된 RR 스냅샷을 만들지 않습니다.
        try{commands.verifyStorage();}catch(org.springframework.dao.DataAccessException exception){throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE);}
        if(commands.abortedAt(commandId,userId)!=null) return;
        var at=now();
        if(!ReservedOrderAbortRules.candidate(c,d) || at.isBefore(d.reservedAt())
            || journal.abortReserved(commandId,userId,d.executionKey())!=1) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"전송이 이미 시작됐거나 미시작 소유권을 확인할 수 없습니다. 차단을 유지합니다.");
        }
        if(journal.auditAbort(commandId,userId,d.executionKey(),c.accountFingerprint(),at)!=1 || commands.abortedAt(commandId,userId)==null) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR,"예약 중단 감사를 저장하지 못했습니다. 상태를 새로고침하세요.");
        }
    }

    private void apply(Long userId, String commandId, boolean recovery) {
        if (commands.lockUser(userId) == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        var command = commands.lockCommand(commandId,userId);
        if (command == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        if (recovery && !binding.matches(command.accountFingerprint())) throw new ApiException(ErrorCode.VALIDATION_ERROR,"승인 당시 계좌 설정과 다릅니다.");
        var record = journal.lock(commandId,userId);
        if(record!=null && "ABORTED".equals(record.phase()) && commands.abortedAt(commandId,userId)!=null) return;
        var receipt = record == null ? null : record.receipt();
        if (!"SENDING".equals(command.status())) {
            if (receipt != null && receipt.valid() && command.status().equals(receipt.status())
                && receipt.orderNo().equals(command.orderNo())) return;
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"주문 상태와 저장 결과가 다릅니다. 차단 상태를 임의로 변경하지 않습니다.");
        }
        OrderDispatchReceipt.requireReplayable(command.status(),record == null ? null : record.phase(),receipt);
        if (commands.finish(commandId,userId,receipt.status(),receipt.orderNo(),receipt.resultCode(),receipt.processCode(),now()) != 1) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE,"주문 상태가 변경되었습니다. 기록을 다시 조회하세요.");
        }
        if (recovery && journal.audit(commandId,userId,receipt.status(),receipt.orderNo(),now()) != 1) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR,"복구 감사 기록을 저장하지 못했습니다.");
        }
    }

    public Status status(Long userId, String commandId) {
        try { commands.verifyStorage(); }
        catch(org.springframework.dao.DataAccessException exception) { throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE); }
        var command=commands.find(commandId,userId);
        if(command==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        var record=journal.find(commandId,userId);
        var receipt=record==null?null:record.receipt();
        var abortedAt=commands.abortedAt(commandId,userId);
        boolean abortable=ReservedOrderAbortRules.candidate(command,record) && binding.matches(command.accountFingerprint());
        boolean recoverable="SENDING".equals(command.status()) && record!=null && "RETURNED".equals(record.phase())
            && receipt!=null && receipt.valid() && binding.matches(command.accountFingerprint());
        String phase=record==null?"LEGACY_UNVERIFIED":record.phase();
        String message=switch(phase) {
            case "ABORTED" -> abortedAt!=null ? "전송 시작 전에 로컬 예약을 중단했습니다. KB 호출과 원본 SENDING의 재전송을 차단하고, 이 명령만 신규 전송 차단 집계에서 제외합니다. 제출/원주문 변경 가드는 보존합니다."
                : "예약 중단 감사와 실행 소유권을 확인하지 못했습니다. 차단을 유지합니다.";
            case "RESERVED" -> "전송 시작 기록이 없습니다. 실행자가 뒤늦게 진행할 수 있어 잠금을 유지합니다.";
            case "DISPATCHING" -> "전송 시작은 기록됐지만 종료 결과가 없습니다. 진행 중 또는 중단 여부를 확정할 수 없어 잠금을 유지합니다.";
            case "RETURNED" -> recoverable ? "종료된 호출의 저장 결과로 상태를 복구할 수 있습니다. UNKNOWN이면 복구 후에도 신규 전송은 차단됩니다."
                : "저장 결과를 확인했습니다. 현재 상태·계좌 설정을 확인하세요.";
            default -> "SENDING".equals(command.status()) ? "이전 버전 기록으로 전송 진행 여부를 증명할 수 없습니다. 잠금을 유지하고 KB 앱에서 확인하세요."
                : "이전 버전의 전송 단계 기록이 없습니다. 저장된 주문 이력과 KB 앱을 확인하세요.";
        };
        return new Status(commandId,command.status(),phase,receipt,record==null?null:record.reservedAt(),
            record==null?null:record.startedAt(),record==null?null:record.returnedAt(),journal.recoveredAt(commandId,userId),recoverable,message,abortable,ReservedOrderAbortResponse.from(abortedAt));
    }
    private LocalDateTime now(){return LocalDateTime.now(ZoneId.of("Asia/Seoul"));}
    public record Status(String commandId,String commandStatus,String phase,OrderDispatchReceipt receipt,
        LocalDateTime reservedAt,LocalDateTime startedAt,LocalDateTime returnedAt,LocalDateTime recoveredAt,boolean recoverable,String message,
        boolean abortable,ReservedOrderAbortResponse reservationAbort){}
}
