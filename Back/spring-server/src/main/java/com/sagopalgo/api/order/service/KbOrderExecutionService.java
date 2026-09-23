package com.sagopalgo.api.order.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.order.dto.KbOrderExecutionItemResponse;
import com.sagopalgo.api.order.dto.KbOrderExecutionPageResponse;
import com.sagopalgo.api.order.dto.KbOrderDateScanResponse;
import com.sagopalgo.api.order.dto.KbOrderLookupResponse;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/** KB 체결미체결 조회를 정규화합니다. 이 서비스는 주문을 전송하거나 재시도하지 않습니다. */
@Service
public class KbOrderExecutionService {
    private static final int MAX_LOOKUP_PAGES = 10;
    private static final int MAX_DATE_SCAN_ITEMS = 200;
    private static final int MAX_NEXT_KEY_LENGTH = 40;
    private static final ZoneId KOREA_TIME = ZoneId.of("Asia/Seoul");

    private final KbSecuritiesAccountClient kbClient;

    public KbOrderExecutionService(KbSecuritiesAccountClient kbClient) {
        this.kbClient = kbClient;
    }

    public KbOrderExecutionPageResponse page(String orderDate, String classification, String nextKey) {
        String date = validDate(orderDate);
        String safeClassification = validClassification(classification);
        String cursor = validNextKey(nextKey);
        JsonNode response = kbClient.fetchOrderExecutions(date, safeClassification, cursor);
        JsonNode body = response == null ? null : response.path("dataBody");
        JsonNode records = body == null ? null : body.path("Record1");
        if (records == null || !records.isArray()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회 응답의 Record1이 올바르지 않습니다.");
        }

        List<KbOrderExecutionItemResponse> items = new ArrayList<>();
        for (JsonNode record : records) {
            items.add(item(record));
        }
        String rawKey = body.path("nxt_key").asText("");
        String returnedKey = rawKey.isBlank() ? "" : rawKey;
        if (returnedKey.length() > MAX_NEXT_KEY_LENGTH) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회의 다음키가 올바르지 않습니다.");
        }
        return new KbOrderExecutionPageResponse(
            date, safeClassification, text(body, "cn_clsf"), returnedKey, List.copyOf(items)
        );
    }

    public KbOrderLookupResponse findByOrderNumber(String orderDate, String orderNo) {
        String date = validDate(orderDate);
        if (orderNo == null || !orderNo.matches("[0-9]{10}") || orderNo.matches("0+")) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB 주문번호는 0이 아닌 숫자 10자리여야 합니다.");
        }
        List<KbOrderExecutionItemResponse> matches = new ArrayList<>();
        Set<String> seenKeys = new HashSet<>();
        String nextKey = "";
        for (int pageNumber = 1; pageNumber <= MAX_LOOKUP_PAGES; pageNumber++) {
            KbOrderExecutionPageResponse result = page(date, "0", nextKey);
            result.items().stream()
                .filter(item -> orderNo.equals(item.orderNo()))
                .forEach(matches::add);
            nextKey = result.nextKey();
            if (nextKey.isEmpty()) {
                return new KbOrderLookupResponse(
                    date, orderNo, result.continuationFlag().isEmpty(), pageNumber, List.copyOf(matches)
                );
            }
            if (!seenKeys.add(nextKey)) {
                return new KbOrderLookupResponse(date, orderNo, false, pageNumber, List.copyOf(matches));
            }
        }
        return new KbOrderLookupResponse(date, orderNo, false, MAX_LOOKUP_PAGES, List.copyOf(matches));
    }

    public KbOrderDateScanResponse scanDate(String orderDate) {
        String date = validDate(orderDate);
        List<KbOrderExecutionItemResponse> items = new ArrayList<>();
        Set<String> seenKeys = new HashSet<>();
        String nextKey = "";
        for (int pageNumber = 1; pageNumber <= MAX_LOOKUP_PAGES; pageNumber++) {
            KbOrderExecutionPageResponse result = page(date, "0", nextKey);
            int remaining = MAX_DATE_SCAN_ITEMS - items.size();
            if (result.items().size() > remaining) {
                items.addAll(result.items().subList(0, remaining));
                return new KbOrderDateScanResponse(date, false, pageNumber, true, List.copyOf(items));
            }
            items.addAll(result.items());
            nextKey = result.nextKey();
            if (nextKey.isEmpty()) {
                return new KbOrderDateScanResponse(
                    date, result.continuationFlag().isEmpty(), pageNumber, false, List.copyOf(items)
                );
            }
            if (items.size() == MAX_DATE_SCAN_ITEMS) {
                return new KbOrderDateScanResponse(date, false, pageNumber, true, List.copyOf(items));
            }
            if (!seenKeys.add(nextKey)) {
                return new KbOrderDateScanResponse(date, false, pageNumber, false, List.copyOf(items));
            }
        }
        return new KbOrderDateScanResponse(date, false, MAX_LOOKUP_PAGES, false, List.copyOf(items));
    }

    private KbOrderExecutionItemResponse item(JsonNode record) {
        if (record == null || !record.isObject()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회 항목이 올바르지 않습니다.");
        }
        String orderNo = text(record, "ordr_no");
        if (!orderNo.matches("[0-9]{10}")) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회 항목에 주문번호가 없습니다.");
        }
        BigDecimal orderQuantity = quantity(record, "ordr_q");
        BigDecimal filledQuantity = quantity(record, "tl_ccls_q");
        BigDecimal openQuantity = quantity(record, "nccls_q");
        String rejectionReason = text(record, "rfsl_rsn_nm");
        return new KbOrderExecutionItemResponse(
            orderNo,
            text(record, "stnd_is_no"),
            text(record, "hngl_shrt_nm"),
            text(record, "trd_dl_ccd_nm"),
            text(record, "ordr_tm"),
            orderQuantity,
            filledQuantity,
            openQuantity,
            optionalDecimal(record, "ordr_uprc"),
            optionalDecimal(record, "ccls_uprc"),
            rejectionReason,
            status(orderQuantity, filledQuantity, openQuantity, rejectionReason)
        );
    }

    private String status(BigDecimal ordered, BigDecimal filled, BigDecimal open, String rejectionReason) {
        if (StringUtils.hasText(rejectionReason) || ordered.signum() <= 0
            || filled.add(open).compareTo(ordered) != 0) {
            return "UNKNOWN";
        }
        if (filled.compareTo(ordered) == 0) {
            return "FILLED";
        }
        if (filled.signum() > 0) {
            return "PARTIAL";
        }
        return "OPEN";
    }

    private BigDecimal quantity(JsonNode node, String field) {
        String value = text(node, field);
        if (!value.matches("[0-9]+")) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회 수량이 올바르지 않습니다: " + field);
        }
        return new BigDecimal(value);
    }

    private BigDecimal optionalDecimal(JsonNode node, String field) {
        String value = text(node, field);
        if (value.isEmpty()) {
            return null;
        }
        try {
            return new BigDecimal(value);
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB 주문 조회 가격이 올바르지 않습니다: " + field);
        }
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.path(field);
        return value.isMissingNode() || value.isNull() ? "" : value.asText().trim();
    }

    private String validDate(String orderDate) {
        if (!StringUtils.hasText(orderDate)) {
            return LocalDate.now(KOREA_TIME).format(DateTimeFormatter.BASIC_ISO_DATE);
        }
        try {
            return LocalDate.parse(orderDate, DateTimeFormatter.BASIC_ISO_DATE)
                .format(DateTimeFormatter.BASIC_ISO_DATE);
        } catch (DateTimeParseException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "주문일자는 yyyyMMdd 형식이어야 합니다.");
        }
    }

    private String validClassification(String classification) {
        String value = StringUtils.hasText(classification) ? classification.trim() : "0";
        if (!List.of("0", "1", "2").contains(value)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "체결구분은 0(전체), 1(체결), 2(미체결) 중 하나여야 합니다.");
        }
        return value;
    }

    private String validNextKey(String nextKey) {
        String value = nextKey == null || nextKey.isBlank() ? "" : nextKey;
        if (value.length() > MAX_NEXT_KEY_LENGTH) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "다음키는 40자 이하여야 합니다.");
        }
        return value;
    }
}
