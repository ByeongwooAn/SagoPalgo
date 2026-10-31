package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.mapper.ManualOrderMapper;
import com.sagopalgo.api.order.mapper.ManualOrderReconciliationMapper;
import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

/** 확인 토큰 소비와 감사 기록만 원자적으로 저장합니다. 원주문·가드 상태는 바꾸지 않습니다. */
@Service
public class ManualOrderReconciliationStore {
    private final ManualOrderMapper commands;
    private final ManualOrderReconciliationMapper reconciliations;

    public ManualOrderReconciliationStore(ManualOrderMapper commands, ManualOrderReconciliationMapper reconciliations) {
        this.commands = commands;
        this.reconciliations = reconciliations;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void confirm(ManualOrderReconciliationRecord record, String tokenHash, LocalDateTime now) {
        if (commands.lockUser(record.userId()) == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        }
        var command = commands.lockCommand(record.commandId(), record.userId());
        if (command == null || !"UNKNOWN".equals(command.status()) || !"NEW".equals(command.kind())
            || !record.accountFingerprint().equals(command.accountFingerprint())
            || !record.orderDate().equals(command.orderDate())
            || command.quantity().compareTo(record.filledQuantity()) != 0
            || reconciliations.find(record.commandId(), record.userId()) != null
            || reconciliations.brokerOrderAlreadyRecorded(record) != 0) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "주문 상태가 바뀌었거나 이미 대조한 주문입니다.");
        }
        if (reconciliations.consume(record.commandId(), record.userId(), tokenHash, record.accountFingerprint(), now) != 1) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "대조 확인이 만료되었거나 이미 사용되었습니다.");
        }
        reconciliations.insert(record);
    }
}
