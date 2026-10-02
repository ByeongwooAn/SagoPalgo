package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.order.dto.OrderReadOnlyProbeResponse;
import com.sagopalgo.api.order.mapper.OrderReadOnlyProbeMapper;
import com.sagopalgo.api.order.model.OrderReadOnlyProbeRecord;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.stereotype.Service;

/** 수동 요청 시 KB 주문 이력 조회 권한만 점검하며 주문은 전송하지 않습니다. */
@Service
public class OrderReadOnlyProbeService {
    private static final ZoneId KOREA_TIME = ZoneId.of("Asia/Seoul");
    private static final Set<String> REQUIRED_CHECKS = Set.of(
        "ACCOUNT_SWITCH", "CREDENTIALS", "ACCOUNT_NUMBER", "HTTPS_ENDPOINT"
    );

    private final OrderReadinessService readinessService;
    private final KbOrderExecutionService executionService;
    private final OrderReadOnlyProbeMapper probeMapper;

    public OrderReadOnlyProbeService(
        OrderReadinessService readinessService,
        KbOrderExecutionService executionService,
        OrderReadOnlyProbeMapper probeMapper
    ) {
        this.readinessService = readinessService;
        this.executionService = executionService;
        this.probeMapper = probeMapper;
    }

    public OrderReadOnlyProbeResponse probe(Long userId) {
        String date = LocalDate.now(KOREA_TIME).format(DateTimeFormatter.BASIC_ISO_DATE);
        if (readinessService.status().checks().stream()
            .filter(check -> REQUIRED_CHECKS.contains(check.code()))
            .anyMatch(check -> !check.passed())) {
            return record(userId, "CONFIGURATION_BLOCKED", date);
        }
        try {
            executionService.page(date, "0", "");
            return record(userId, "VERIFIED", date);
        } catch (ApiException exception) {
            return record(userId, "UNVERIFIED", date);
        }
    }

    public Optional<OrderReadOnlyProbeResponse> latest(Long userId) {
        return probeMapper.findLatest(userId).map(this::toResponse);
    }

    public List<OrderReadOnlyProbeResponse> history(Long userId) {
        return probeMapper.findRecent(userId).stream().map(this::toResponse).toList();
    }

    private OrderReadOnlyProbeResponse record(Long userId, String status, String date) {
        LocalDateTime checkedAt = LocalDateTime.now(KOREA_TIME);
        probeMapper.insert(new OrderReadOnlyProbeRecord(userId, status, date, checkedAt));
        return new OrderReadOnlyProbeResponse(status, date, checkedAt, true, message(status));
    }

    private OrderReadOnlyProbeResponse toResponse(OrderReadOnlyProbeRecord item) {
        return new OrderReadOnlyProbeResponse(
            item.status(), item.orderDate(), item.checkedAt(), true, message(item.status())
        );
    }

    private String message(String status) {
        return switch (status) {
            case "VERIFIED" -> "KB 체결·미체결 조회 응답을 확인했습니다. 주문 권한이나 전송 가능 상태를 뜻하지 않습니다.";
            case "CONFIGURATION_BLOCKED" -> "KB 계좌 조회 설정을 확인해 주세요.";
            default -> "읽기 전용 조회를 확인하지 못했습니다. KB API 권한·네트워크·응답 형식을 확인해 주세요.";
        };
    }
}
