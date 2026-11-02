package com.sagopalgo.api.kb.service;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** 저장할 서버 생성 계약만 직렬화하며 원문 JSON의 무결성을 검증합니다. */
@Component
public class AccountObservationCodec {
    private final ObjectMapper json;

    public AccountObservationCodec(ObjectMapper objectMapper) {
        json = objectMapper.copy().disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }

    public record Encoded(String payload, String sha256) {}

    public Encoded encode(KbAccountSnapshotResponse snapshot, String date) {
        try {
            validate(snapshot, date);
            String payload = json.writeValueAsString(snapshot);
            return new Encoded(payload, hash(payload));
        } catch (Exception exception) {
            throw new IllegalArgumentException("저장할 계좌 관찰 계약이 올바르지 않습니다.");
        }
    }

    public KbAccountSnapshotResponse decode(AccountObservationRecord record) {
        if (!"COMPLETED".equals(record.storageState())) return null;
        try {
            if (record.payload() == null || !hash(record.payload()).equals(record.payloadSha256())) {
                throw new IllegalArgumentException();
            }
            KbAccountSnapshotResponse result = json.readValue(record.payload(), KbAccountSnapshotResponse.class);
            validate(result, record.orderDate());
            if (!result.observationId().equals(record.observationId()) || !result.status().name().equals(record.snapshotStatus())) {
                throw new IllegalArgumentException();
            }
            return result;
        } catch (Exception exception) {
            // 손상된 JSON·SQL 예외에 금융 데이터가 들어 있을 수 있어 원문/cause를 외부에 복사하지 않습니다.
            throw new ApiException(ErrorCode.OBSERVATION_STORAGE_UNAVAILABLE);
        }
    }

    private void validate(KbAccountSnapshotResponse value, String date) {
        if (value == null || !"KB_ACCOUNT_OBSERVATION_V1".equals(value.contractVersion())
            || !"KB".equals(value.provider()) || !"primary".equals(value.accountAlias())
            || value.atomic() || value.usableForTrading() || value.status() == null
            || value.startedAt() == null || value.completedAt() == null || value.startedAt().isAfter(value.completedAt())
            || value.sections() == null || value.sections().size() != 4
            || !UUID.fromString(value.observationId()).toString().equals(value.observationId())) {
            throw new IllegalArgumentException();
        }
        List<String> sources = List.of("SSQM1801", "SSQM2932", "SSQM2952", "SSQM2341");
        for (int i = 0; i < 4; i++) {
            var section = value.sections().get(i);
            if (section == null || !sources.get(i).equals(section.api()) || section.status() == null
                || section.completeness() == null || section.scope() == null || section.summary() == null
                || section.rows() == null || section.rows().size() > 500 || section.issues() == null
                || section.pagesRead() < 0 || section.pagesRead() > 10 || section.receivedRowCount() < 0
                || section.startedAt() == null || section.completedAt() == null
                || section.startedAt().isAfter(section.completedAt())) throw new IllegalArgumentException();
        }
        if (!date.equals(value.sections().get(3).scope().get("orderDate"))) throw new IllegalArgumentException();
    }

    private String hash(String payload) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(payload.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException exception) { throw new IllegalStateException(); }
    }
}
