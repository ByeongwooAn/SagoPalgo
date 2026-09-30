package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.OrderSubmissionStatusResponse;
import com.sagopalgo.api.order.mapper.OrderSubmissionGuardMapper;
import com.sagopalgo.api.order.model.OrderSubmissionGuardRecord;
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;

/** 향후 주문 전송자가 사용할 단일 제출 예약입니다. 이 서비스는 KB API를 호출하지 않습니다. */
@Service
public class OrderSubmissionGuardService {
    private final OrderSubmissionGuardMapper mapper;
    private final OrderAccountBinding accountBinding;

    public OrderSubmissionGuardService(OrderSubmissionGuardMapper mapper, OrderAccountBinding accountBinding) {
        this.mapper = mapper;
        this.accountBinding = accountBinding;
    }

    public void reserveOnce(Long userId, Long approvalId) {
        if (mapper.reserveOnce(approvalId, userId, accountBinding.requireFingerprint(), LocalDateTime.now()) != 1) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "제출 예약이 만료·사용되었거나 승인 기록이 없습니다.");
        }
    }

    public void markUncertain(Long userId, Long approvalId) {
        if (mapper.markUncertain(approvalId, userId, LocalDateTime.now()) != 1) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "예약된 제출만 확인 필요 상태로 바꿀 수 있습니다.");
        }
    }

    public OrderSubmissionStatusResponse status(Long userId, Long approvalId) {
        OrderSubmissionGuardRecord record = mapper.findByApprovalId(approvalId, userId);
        if (record == null) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "해당 주문 승인 기록을 찾을 수 없습니다.");
        }
        String status = record.getStatus();
        if ("READY".equals(status)
            && (record.getExpiresAt() == null || !record.getExpiresAt().isAfter(LocalDateTime.now()))) {
            status = "EXPIRED";
        } else if ("READY".equals(status) && !accountBinding.matches(record.getAccountFingerprint())) {
            status = "ACCOUNT_CHANGED";
        }
        return new OrderSubmissionStatusResponse(
            record.getOrderApprovalId(), status, record.getExpiresAt(),
            record.getReservedAt(), record.getUncertainAt()
        );
    }
}
