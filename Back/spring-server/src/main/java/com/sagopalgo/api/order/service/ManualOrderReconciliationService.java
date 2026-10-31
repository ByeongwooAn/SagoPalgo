package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse;
import com.sagopalgo.api.order.dto.ManualOrderReconciliationResponse;
import com.sagopalgo.api.order.dto.ManualOrderResponse;
import com.sagopalgo.api.order.mapper.ManualOrderMapper;
import com.sagopalgo.api.order.mapper.ManualOrderReconciliationMapper;
import com.sagopalgo.api.order.model.ManualOrderCommand;
import com.sagopalgo.api.order.model.ManualOrderReconciliationPreparation;
import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.SecureRandom;
import java.time.*;
import java.time.format.*;
import java.time.temporal.ChronoField;
import java.util.Base64;
import java.util.HexFormat;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

/** 전송이 끝나 UNKNOWN인 신규 주문의 전량 체결만 사용자 확인으로 대조합니다. 주문 HTTP는 호출하지 않습니다. */
@Service
public class ManualOrderReconciliationService {
    private static final ZoneId KST = ZoneId.of("Asia/Seoul");
    private static final DateTimeFormatter ORDER_TIME = new DateTimeFormatterBuilder()
        .appendValue(ChronoField.HOUR_OF_DAY, 2).appendValue(ChronoField.MINUTE_OF_HOUR, 2)
        .appendValue(ChronoField.SECOND_OF_MINUTE, 2).toFormatter().withResolverStyle(ResolverStyle.STRICT);
    private final ManualOrderMapper commands;
    private final ManualOrderReconciliationMapper mapper;
    private final OrderAccountBinding binding;
    private final KbOrderExecutionService executions;
    private final ManualOrderReconciliationStore store;

    public ManualOrderReconciliationService(ManualOrderMapper commands, ManualOrderReconciliationMapper mapper,
        OrderAccountBinding binding, KbOrderExecutionService executions, ManualOrderReconciliationStore store) {
        this.commands = commands;
        this.mapper = mapper;
        this.binding = binding;
        this.executions = executions;
        this.store = store;
    }

    public Preparation prepare(Long userId, String commandId, String orderNo) {
        var command = requireCandidate(userId, commandId);
        var row = verifiedFilledOrder(command, orderNo);
        var now = LocalDateTime.now(KST);
        byte[] bytes = new byte[32];
        new SecureRandom().nextBytes(bytes);
        String token = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes);
        mapper.prepare(new ManualOrderReconciliationPreparation(commandId, userId, command.accountFingerprint(),
            orderNo, hash(token), now.plusSeconds(90), now));
        return new Preparation(ManualOrderResponse.from(command), orderNo, row.orderTime(), row.filledQuantity(),
            token, now.plusSeconds(90), "KB 앱에서 확인한 원주문인지 직접 확인하세요. 확정해도 주문을 다시 전송하지 않습니다.");
    }

    public ManualOrderReconciliationResponse confirm(Long userId, String commandId, String token,
        boolean acknowledged, String confirmation) {
        if (!acknowledged || !"전량 체결 대조 확정".equals(confirmation) || token == null || token.length() > 200) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB 원주문과 전량 체결 확인이 필요합니다.");
        }
        var command = requireCandidate(userId, commandId);
        var preparation = mapper.preparation(commandId, userId);
        var now = LocalDateTime.now(KST);
        if (preparation == null || !preparation.expiresAt().isAfter(now)
            || !binding.matches(preparation.accountFingerprint())
            || !MessageDigest.isEqual(hash(token).getBytes(StandardCharsets.US_ASCII),
                preparation.tokenHash().getBytes(StandardCharsets.US_ASCII))) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "대조 확인이 만료되었거나 유효하지 않습니다.");
        }
        var row = verifiedFilledOrder(command, preparation.orderNo());
        // 조회 중 계좌 설정이 바뀌었으면 토큰을 소비하지 않습니다.
        if (!binding.matches(command.accountFingerprint())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "승인 당시 계좌 설정과 다릅니다.");
        }
        var record = new ManualOrderReconciliationRecord(commandId, userId, command.accountFingerprint(),
            command.orderDate(), preparation.orderNo(), row.orderTime(), row.filledQuantity(), LocalDateTime.now(KST));
        store.confirm(record, hash(token), LocalDateTime.now(KST));
        return ManualOrderReconciliationResponse.from(record);
    }

    private ManualOrderCommand requireCandidate(Long userId, String id) {
        try { commands.verifyStorage(); }
        catch (DataAccessException exception) { throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE); }
        var command = commands.find(id, userId);
        if (command == null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        if (!"UNKNOWN".equals(command.status()) || !"NEW".equals(command.kind())
            || mapper.find(id, userId) != null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR,
                "미확정 신규 주문만 대조할 수 있습니다. 전송 중·정정·취소 주문은 별도 확인이 필요합니다.");
        }
        if (!binding.matches(command.accountFingerprint())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "승인 당시 계좌 설정과 다릅니다.");
        }
        return command;
    }

    private KbOrderExecutionItemResponse verifiedFilledOrder(ManualOrderCommand command, String orderNo) {
        if (orderNo == null || !orderNo.matches("[0-9]{10}") || orderNo.matches("0+")) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB 앱에서 확인한 숫자 10자리 주문번호를 입력하세요.");
        }
        var lookup = executions.findByOrderNumber(command.orderDate(), orderNo);
        if (!lookup.completeScan() || lookup.matches().size() != 1
            || !orderNo.equals(lookup.orderNo()) || !command.orderDate().equals(lookup.orderDate())) {
            throw mismatch();
        }
        var row = lookup.matches().get(0);
        if (!orderNo.equals(row.orderNo()) || !command.stockCode().equals(row.stockCode())
            || !("BUY".equals(command.side()) ? "매수" : "매도").equals(row.tradeTypeName())
            || !"FILLED".equals(row.status()) || row.orderPrice() == null || row.orderQuantity() == null
            || row.filledQuantity() == null || row.openQuantity() == null
            || row.rejectionReason() == null || !row.rejectionReason().isBlank()
            || command.price().compareTo(row.orderPrice()) != 0
            || command.quantity().compareTo(row.orderQuantity()) != 0
            || command.quantity().compareTo(row.filledQuantity()) != 0 || row.openQuantity().signum() != 0
            || !timeMatches(command, row.orderTime()) || UnknownOrderReviewRules.hasChangeEvidence(row)) {
            throw mismatch();
        }
        var evidence = new ManualOrderReconciliationRecord(command.commandId(), command.userId(), command.accountFingerprint(),
            command.orderDate(), orderNo, row.orderTime(), row.filledQuantity(), LocalDateTime.now(KST));
        if (mapper.brokerOrderAlreadyRecorded(evidence) != 0) throw mismatch();
        return row;
    }

    private boolean timeMatches(ManualOrderCommand command, String value) {
        try {
            var brokerTime = LocalDate.parse(command.orderDate(), DateTimeFormatter.BASIC_ISO_DATE)
                .atTime(LocalTime.parse(value, ORDER_TIME));
            long seconds = Duration.between(command.createdAt(), brokerTime).getSeconds();
            return seconds >= -2 && seconds <= 300;
        } catch (DateTimeException | NullPointerException exception) { return false; }
    }

    private ApiException mismatch() {
        return new ApiException(ErrorCode.VALIDATION_ERROR,
            "주문일·종목·방향·단가·수량·주문 시각 및 전량 체결을 대조하지 못했습니다. 잠금은 유지됩니다.");
    }

    private String hash(String value) {
        try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8))); }
        catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(exception); }
    }

    public record Preparation(ManualOrderResponse command, String orderNo, String orderTime,
        java.math.BigDecimal filledQuantity, String token, LocalDateTime expiresAt, String message) {}
}
