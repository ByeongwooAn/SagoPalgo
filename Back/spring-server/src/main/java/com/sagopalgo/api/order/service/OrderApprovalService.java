package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmRequest;
import com.sagopalgo.api.order.dto.OrderApprovalConfirmResponse;
import com.sagopalgo.api.order.dto.OrderApprovalPrepareResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderPrecheckResponse;
import com.sagopalgo.api.order.mapper.OrderApprovalMapper;
import com.sagopalgo.api.order.mapper.OrderSubmissionGuardMapper;
import com.sagopalgo.api.order.model.OrderApprovalRecord;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.LocalDateTime;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/** 수동 승인 기록까지만 처리하며 KB 주문 API는 호출하지 않습니다. */
@Service
public class OrderApprovalService {
    private static final int TOKEN_BYTES = 32;
    private static final int TOKEN_TTL_SECONDS = 90;
    private static final int RESERVATION_TTL_SECONDS = 90;
    private static final String NOT_SUBMITTED = "승인 기록만 저장되었습니다. KB증권에 실제 주문은 전송되지 않았습니다.";

    private final OrderPrecheckService precheckService;
    private final OrderApprovalMapper mapper;
    private final OrderSubmissionGuardMapper submissionGuardMapper;
    private final SecureRandom secureRandom = new SecureRandom();

    public OrderApprovalService(
        OrderPrecheckService precheckService,
        OrderApprovalMapper mapper,
        OrderSubmissionGuardMapper submissionGuardMapper
    ) {
        this.precheckService = precheckService;
        this.mapper = mapper;
        this.submissionGuardMapper = submissionGuardMapper;
    }

    public OrderApprovalPrepareResponse prepare(Long userId, OrderPrecheckRequest request) {
        KbLimitOrderContract.requireSupported(request);
        OrderPrecheckResponse precheck = precheckService.precheck(userId, request);
        if (!precheck.eligible()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "안전 조건을 통과하지 못해 승인할 수 없습니다.");
        }

        byte[] tokenBytes = new byte[TOKEN_BYTES];
        secureRandom.nextBytes(tokenBytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(tokenBytes);
        LocalDateTime now = LocalDateTime.now();
        OrderApprovalRecord record = new OrderApprovalRecord();
        record.setUserId(userId);
        record.setOrderPrecheckId(precheck.orderPrecheckId());
        record.setTokenHash(hash(token));
        record.setCreatedAt(now);
        record.setExpiresAt(now.plusSeconds(TOKEN_TTL_SECONDS));
        mapper.insert(record);
        return new OrderApprovalPrepareResponse(
            record.getOrderApprovalId(), token, record.getExpiresAt(), precheck,
            "90초 안에 주문안을 확인해 승인할 수 있습니다. 이 단계에서는 실제 주문이 전송되지 않습니다."
        );
    }

    @Transactional
    public OrderApprovalConfirmResponse confirm(Long userId, OrderApprovalConfirmRequest request) {
        if (!request.acknowledged()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "실주문 미전송 안내를 확인해야 합니다.");
        }
        LocalDateTime now = LocalDateTime.now();
        int changed = mapper.acknowledge(request.approvalId(), userId, hash(request.token()), now);
        if (changed != 1) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "승인 토큰이 만료되었거나 이미 사용되었습니다. 다시 검증해 주세요.");
        }
        if (submissionGuardMapper.insertReady(
            request.approvalId(), userId, now, now.plusSeconds(RESERVATION_TTL_SECONDS)
        ) != 1) {
            throw new ApiException(ErrorCode.INTERNAL_ERROR, "제출 가드 기록을 만들 수 없어 승인을 저장하지 않았습니다.");
        }
        return new OrderApprovalConfirmResponse(request.approvalId(), "ACKNOWLEDGED", false, NOT_SUBMITTED);
    }

    private String hash(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256을 사용할 수 없습니다.", exception);
        }
    }
}
