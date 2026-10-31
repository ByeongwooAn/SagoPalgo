package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.ManualOrderCommand;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** 외부 HTTP 호출 전에 반드시 독립 트랜잭션을 커밋합니다. 전송 후에는 READY로 되돌리지 않습니다. */
@Service
public class ManualOrderStore {
    private final ManualOrderMapper mapper;
    private final OrderSubmissionGuardMapper guards;
    private final ManualOrderDispatchMapper dispatches;
    public ManualOrderStore(ManualOrderMapper mapper, OrderSubmissionGuardMapper guards, ManualOrderDispatchMapper dispatches) {
        this.mapper=mapper; this.guards=guards; this.dispatches=dispatches;
    }

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public void claim(ManualOrderCommand command) {
        claim(command,java.util.UUID.randomUUID().toString());
    }

    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public void claim(ManualOrderCommand command, String executionKey) {
        if (mapper.lockUser(command.userId()) == null || mapper.pending(command.userId()) != 0) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "확인되지 않은 전송이 있습니다. KB 앱과 주문 기록을 확인하세요.");
        }
        if ("NEW".equals(command.kind())) {
            if (guards.reserveOnce(command.approvalId(), command.userId(), command.accountFingerprint(), LocalDateTime.now()) != 1) {
                throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "만료되었거나 이미 사용한 승인입니다.");
            }
            mapper.insert(command);
        } else {
            LocalDateTime now=LocalDateTime.now(java.time.ZoneId.of("Asia/Seoul"));
            if (mapper.claimParent(command.parentId(),command.commandId(),command.userId(),now)!=1
                || mapper.claimChange(command.commandId(),command.userId(),command.tokenHash(),command.accountFingerprint(),now)!=1) {
                throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "정정·취소 승인이 만료되었거나 이미 사용되었습니다.");
            }
        }
        if(dispatches.reserve(command.commandId(),command.userId(),executionKey,
            LocalDateTime.now(java.time.ZoneId.of("Asia/Seoul")))!=1) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR,"전송 예약 기록을 저장하지 못했습니다. 주문을 전송하지 않습니다.");
        }
    }
}
