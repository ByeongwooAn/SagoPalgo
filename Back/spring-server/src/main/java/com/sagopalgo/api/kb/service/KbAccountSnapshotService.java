package com.sagopalgo.api.kb.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Completeness;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Issue;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Row;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Section;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.Status;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.time.format.ResolverStyle;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

/**
 * KB 조회만 순차 실행하는 무상태 관찰 경계입니다. 기존 화면용 반올림/누락값 0 치환을 사용하지
 * 않으며 Mapper, 주문 실행·승인·가드·원장 서비스에 의존하지 않습니다.
 */
@Service
public class KbAccountSnapshotService {
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");
    private static final int MAX_PAGES = 10;
    private static final int MAX_ROWS = 500;
    private static final DateTimeFormatter PROCESS_TIME = DateTimeFormatter
        .ofPattern("uuuuMMddHHmmssSSS").withResolverStyle(ResolverStyle.STRICT);

    private enum Source {
        HOLDINGS("SSQM1801", 12,
            "is_no is_nm", "gnrl_q ordr_psbl_q", "gnrl_q ordr_psbl_q"),
        SETTLEMENT("SSQM2932", 0,
            "gds_typ clsf crncy_cd is_cd is_nm is_dtl_typ_cd fnl_ccls_excg_cd",
            "blnc_q blnc_q_p6 ordr_psbl_q ordr_psbl_q_p6 now_prc byng_avr_prc val_amt pl_amt yld val_sgrvt_p2",
            "tfnd o_amt_psbl_amt ordr_psbl_csh byng_amt_sum pl_amt_sum val_amt_sum yld_sum"),
        EXECUTION("SSQM2952", 0,
            "clsf crncy_cd is_cd is_nm is_dtl_typ_cd fnl_ccls_excg_cd",
            "hld_q hld_q_p6 ordr_psbl_q ordr_psbl_q_p6 nstmt_s_q nstmt_s_q_p6 nstmt_b_q nstmt_b_q_p6 ec_q ec_q_p6 byng_amt now_prc byng_avr_prc val_amt val_pl val_yld",
            "dy_tfnd ndy_tfnd nxt2_dy_tfnd nt_asts_val_amt scrts_nt_val_amt ndy_o_amt_psbl_amt byng_amt_sum val_amt_sum val_pl_sum val_yld_sum"),
        ORDERS("SSQM2341", 40,
            "orgn_ordr_no stnd_is_no ordr_no trd_dl_ccd_nm hngl_shrt_nm ordr_tm ordr_ccd crct_cncl_ccd sor_ordr_ccd",
            "ordr_q tl_ccls_q nccls_q ordr_uprc ccls_uprc crct_q sor_cncl_q", "s_ccls_amt b_ccls_amt s_ccls_q b_ccls_q");

        final String api;
        final int cursorLength;
        final List<String> textFields;
        final List<String> numbers;
        final List<String> summary;

        Source(String api, int cursorLength, String text, String numbers, String summary) {
            this.api = api;
            this.cursorLength = cursorLength;
            this.textFields = List.of(text.split(" "));
            this.numbers = List.of(numbers.split(" "));
            this.summary = List.of(summary.split(" "));
        }
    }

    private final KbSecuritiesAccountClient client;
    private final SecuritiesProviderProperties properties;
    private final Clock clock;

    @Autowired
    public KbAccountSnapshotService(KbSecuritiesAccountClient client, SecuritiesProviderProperties properties) {
        this(client, properties, Clock.systemUTC());
    }

    KbAccountSnapshotService(KbSecuritiesAccountClient client, SecuritiesProviderProperties properties, Clock clock) {
        this.client = client;
        this.properties = properties;
        this.clock = clock;
    }

    public KbAccountSnapshotResponse observe(String requestedDate) {
        String date = orderDate(requestedDate);
        Instant start = clock.instant();
        List<String> context = context();
        List<Section> sections = new ArrayList<>();
        for (Source source : Source.values()) {
            Map<String, String> scope = scope(source, date);
            if (!properties.getKb().isAccountEnabled()) {
                sections.add(unavailable(source, scope, Status.DISABLED, "ACCOUNT_DISABLED"));
            } else if (!context.equals(context())) {
                sections.add(unavailable(source, scope, Status.FAILED, "CONTEXT_CHANGED"));
            } else {
                sections.add(read(source, scope, date));
            }
        }
        // 어느 조회 도중 연결/조회 설정이 바뀌었으면 다른 계좌의 관찰을 섞어서 내보내지 않습니다.
        if (!context.equals(context())) {
            sections = new ArrayList<>();
            for (Source source : Source.values()) {
                sections.add(unavailable(source, Map.of(), Status.FAILED, "CONTEXT_CHANGED"));
            }
        }
        Status status = sections.stream().allMatch(s -> s.status() == Status.SUCCESS) ? Status.SUCCESS
            : sections.stream().allMatch(s -> s.status() == Status.DISABLED) ? Status.DISABLED
            : sections.stream().allMatch(s -> s.status() == Status.FAILED) ? Status.FAILED : Status.PARTIAL;
        return new KbAccountSnapshotResponse("KB_ACCOUNT_OBSERVATION_V1", UUID.randomUUID().toString(),
            "KB", "primary", start, clock.instant(), status, false, false, List.copyOf(sections));
    }

    private Section read(Source source, Map<String, String> scope, String date) {
        Instant start = clock.instant();
        String processed = null;
        List<Issue> issues = new ArrayList<>();
        List<Row> rows = new ArrayList<>();
        Map<String, String> summary = Map.of();
        Set<String> cursors = new HashSet<>();
        Set<String> identities = new HashSet<>();
        String cursor = "";
        int pages = 0;
        int received = 0;
        Integer reported = null;
        Completeness completeness = Completeness.UNKNOWN;
        try {
            if (!expectedPath(source)) {
                return unavailable(source, scope, Status.FAILED, "UNSUPPORTED_CONTRACT");
            }
            while (pages < MAX_PAGES) {
                JsonNode response = fetch(source, date, cursor);
                JsonNode body = validBody(response);
                pages++;
                processed = processTime(response, issues);
                if (pages == 1) {
                    summary = numericFields(body, source.summary, issues);
                }
                if (source == Source.ORDERS && !date.equals(text(body, "ordr_dt"))) {
                    issues.add(new Issue("SCOPE_MISMATCH", "ordr_dt"));
                    completeness = Completeness.INVALID;
                    break;
                }
                Integer gridCount = count(body, "grid_cnt1", issues);
                if (source.cursorLength == 0) {
                    reported = count(body, "tl_data_cnt", issues);
                }
                JsonNode record = body.get("Record1");
                // 배열 누락은 명시적인 건수 0이 있을 때만 정상 빈 결과로 인정합니다.
                if (record == null || record.isNull()) {
                    if (Integer.valueOf(0).equals(gridCount) || Integer.valueOf(0).equals(reported)) {
                        record = com.fasterxml.jackson.databind.node.JsonNodeFactory.instance.arrayNode();
                    } else {
                        issues.add(new Issue("MISSING_RECORDS", "Record1"));
                        completeness = Completeness.UNKNOWN;
                        break;
                    }
                }
                if (!record.isArray()) {
                    issues.add(new Issue("INVALID_RECORDS", "Record1"));
                    completeness = Completeness.INVALID;
                    break;
                }
                received += record.size();
                if (gridCount != null && gridCount != record.size()) {
                    issues.add(new Issue("COUNT_MISMATCH", "grid_cnt1"));
                }
                int remaining = MAX_ROWS - (received - record.size());
                int inspected = 0;
                for (JsonNode item : record) {
                    if (inspected++ >= remaining) break;
                    if (!item.isObject()) {
                        issues.add(new Issue("INVALID_ROW", "Record1"));
                        continue;
                    }
                    Map<String, String> fields = new LinkedHashMap<>();
                    for (String field : source.textFields) fields.put(field, text(item, field));
                    fields.putAll(numericFields(item, source.numbers, issues));
                    if (source.textFields.stream().allMatch(f -> fields.get(f) == null)) {
                        issues.add(new Issue("MISSING_IDENTITY", "Record1"));
                    }
                    if (source == Source.HOLDINGS && fields.get("gnrl_q") == null) {
                        issues.add(new Issue("MISSING_FIELD", "gnrl_q"));
                    }
                    String identity = text(item, source == Source.HOLDINGS ? "is_no"
                        : source == Source.ORDERS ? "ordr_no" : "is_cd");
                    if (source == Source.HOLDINGS || source == Source.ORDERS) {
                        if (identity == null) issues.add(new Issue("MISSING_IDENTITY", "Record1"));
                        else if (!identities.add(identity)) issues.add(new Issue("DUPLICATE_IDENTITY", "Record1"));
                    }
                    rows.add(new Row(Collections.unmodifiableMap(fields)));
                }
                if (received > MAX_ROWS) {
                    issues.add(new Issue("ROW_LIMIT", "Record1"));
                    completeness = Completeness.PARTIAL;
                    break;
                }
                if (source.cursorLength == 0) {
                    completeness = reported == null ? Completeness.UNKNOWN
                        : reported == record.size() ? Completeness.COMPLETE
                        : reported > record.size() ? Completeness.PARTIAL : Completeness.INVALID;
                    if (reported == null) issues.add(new Issue("MISSING_COUNT", "tl_data_cnt"));
                    else if (reported != record.size()) issues.add(new Issue("COUNT_MISMATCH", "tl_data_cnt"));
                    if (text(body, "nxt_key") != null && !text(body, "nxt_key").isBlank()) {
                        completeness = Completeness.PARTIAL;
                        issues.add(new Issue("UNSUPPORTED_PAGINATION", "nxt_key"));
                    }
                    break;
                }
                JsonNode key = body.get("nxt_key");
                if (key == null || !key.isTextual()) {
                    issues.add(new Issue("MISSING_NEXT_KEY", "nxt_key"));
                    completeness = Completeness.UNKNOWN;
                    break;
                }
                cursor = key.textValue();
                if (cursor.length() > source.cursorLength || cursor.chars().anyMatch(c -> c < 32 || c > 126)) {
                    issues.add(new Issue("INVALID_NEXT_KEY", "nxt_key"));
                    completeness = Completeness.PARTIAL;
                    break;
                }
                if (cursor.isBlank()) {
                    completeness = Completeness.COMPLETE;
                    break;
                }
                completeness = Completeness.PARTIAL;
                if (!cursors.add(cursor)) {
                    issues.add(new Issue("REPEATED_NEXT_KEY", "nxt_key"));
                    break;
                }
                if (pages == MAX_PAGES) issues.add(new Issue("PAGE_LIMIT", "nxt_key"));
            }
        } catch (RuntimeException exception) {
            // 예외 메시지·KB 응답 전문·인증값을 응답이나 로그로 복사하지 않습니다. 재시도도 하지 않습니다.
            issues.add(new Issue("LOOKUP_FAILED", null));
            completeness = pages == 0 ? Completeness.UNKNOWN : Completeness.PARTIAL;
        }
        if (completeness == Completeness.COMPLETE && issues.stream().anyMatch(i -> List.of(
            "COUNT_MISMATCH", "INVALID_COUNT", "INVALID_ROW", "MISSING_IDENTITY", "DUPLICATE_IDENTITY",
            "MISSING_FIELD", "INVALID_NUMBER", "NEGATIVE_QUANTITY").contains(i.code()))) {
            completeness = Completeness.INVALID;
        }
        Status status = pages == 0 ? Status.FAILED
            : completeness == Completeness.COMPLETE && issues.isEmpty() ? Status.SUCCESS : Status.PARTIAL;
        return new Section(source.api, scope, status, completeness, start, clock.instant(), processed,
            pages, received, reported, summary, List.copyOf(rows), List.copyOf(issues));
    }

    private JsonNode fetch(Source source, String date, String cursor) {
        return switch (source) {
            case HOLDINGS -> client.fetchHoldingsPage(cursor);
            case SETTLEMENT -> client.fetchSettlementBalance();
            case EXECUTION -> client.fetchExecutionBalance();
            case ORDERS -> client.fetchOrderExecutions(date, "0", cursor);
        };
    }

    private boolean expectedPath(Source source) {
        Provider kb = properties.getKb();
        return switch (source) {
            case HOLDINGS -> "/api/v1/ssqm1801".equals(kb.getHoldingsPath());
            case SETTLEMENT -> "/api/v1/ssqm2932".equals(kb.getSettlementBalancePath());
            case EXECUTION -> "/api/v1/ssqm2952".equals(kb.getExecutionBalancePath());
            case ORDERS -> true;
        };
    }

    private JsonNode validBody(JsonNode response) {
        if (response == null || !response.path("dataBody").isObject()
            || !"200".equals(response.path("dataHeader").path("resultCode").asText())
            || !"A".equals(response.path("dataHeader").path("processFlag").asText())) {
            throw new IllegalArgumentException("Invalid observation envelope");
        }
        return response.get("dataBody");
    }

    private Map<String, String> numericFields(JsonNode node, List<String> fields, List<Issue> issues) {
        Map<String, String> result = new LinkedHashMap<>();
        for (String field : fields) {
            JsonNode value = node.get(field);
            String number = value == null || value.isNull() ? null
                : value.isTextual() ? value.textValue().trim()
                : value.isIntegralNumber() ? value.asText() : null;
            if (value != null && !value.isNull() && !(value.isTextual() && number.isEmpty())) {
                if (number == null || number.length() > 64
                    || !number.matches("[-+]?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\\.[0-9]+)?")) {
                    issues.add(new Issue("INVALID_NUMBER", field));
                    number = null;
                } else {
                    number = number.replace(",", "");
                    if (field.endsWith("_q") || field.endsWith("_q_p6")) {
                        if (number.startsWith("-")) {
                            issues.add(new Issue("NEGATIVE_QUANTITY", field));
                            number = null;
                        }
                    }
                }
            }
            result.put(field, number == null || number.isBlank() ? null : number);
        }
        return Collections.unmodifiableMap(result);
    }

    private Integer count(JsonNode body, String field, List<Issue> issues) {
        String value = text(body, field);
        if (value == null) return null;
        try {
            if (!value.matches("[0-9]{1,18}")) throw new NumberFormatException();
            return Integer.valueOf(value);
        } catch (NumberFormatException exception) {
            issues.add(new Issue("INVALID_COUNT", field));
            return null;
        }
    }

    private String processTime(JsonNode response, List<Issue> issues) {
        String value = text(response.path("dataHeader"), "processTime");
        if (value == null) return null;
        try {
            if (!value.matches("[0-9]{17}")) throw new DateTimeParseException("Invalid process time", value, 0);
            LocalDateTime.parse(value, PROCESS_TIME);
            // 공개 필드의 시간대를 확인하기 전에는 UTC나 평가 기준 시각으로 변환하지 않습니다.
            return value;
        } catch (DateTimeParseException exception) {
            issues.add(new Issue("INVALID_PROCESS_TIME", "processTime"));
            return null;
        }
    }

    private String text(JsonNode node, String field) {
        JsonNode value = node.get(field);
        if (value == null || value.isNull()) return null;
        if (!value.isTextual() && !value.isIntegralNumber()) return null;
        String result = value.asText().trim();
        return result.isEmpty() ? null : result;
    }

    private Section unavailable(Source source, Map<String, String> scope, Status status, String reason) {
        Instant now = clock.instant();
        return new Section(source.api, scope, status, Completeness.UNKNOWN, now, now, null,
            0, 0, null, Map.of(), List.of(), List.of(new Issue(reason, null)));
    }

    private Map<String, String> scope(Source source, String date) {
        Provider kb = properties.getKb();
        return switch (source) {
            case HOLDINGS -> Map.of("inquiryClassification", safe(kb.getHoldingsInquiryClassification()),
                "marketTimeCode", safe(kb.getHoldingsMarketTimeCode()), "stockFilter", safe(kb.getHoldingsStockCode()));
            case SETTLEMENT -> Map.of("basis", "SETTLEMENT", "inquiryClassification", safe(kb.getBalanceInquiryClassification()),
                "exchangePriceCode", safe(kb.getBalanceExchangeMarketPriceCode()));
            case EXECUTION -> Map.of("basis", "EXECUTION", "exchangePriceCode", safe(kb.getBalanceExchangeMarketPriceCode()));
            case ORDERS -> Map.of("orderDate", date, "executionClassification", "0");
        };
    }

    private List<String> context() {
        Provider kb = properties.getKb();
        return List.of(safe(kb.getBaseUrl()), safe(kb.getTokenPath()), safe(kb.getAppKey()), safe(kb.getAppSecret()),
            safe(kb.getAccountNumber()), safe(kb.getAccountProductCode()), Boolean.toString(kb.isAccountEnabled()),
            safe(kb.getHoldingsPath()), safe(kb.getSettlementBalancePath()), safe(kb.getExecutionBalancePath()),
            safe(kb.getHoldingsInquiryClassification()), safe(kb.getHoldingsMarketTimeCode()), safe(kb.getHoldingsStockCode()),
            safe(kb.getBalanceInquiryClassification()), safe(kb.getBalanceExchangeMarketPriceCode()));
    }

    private String safe(String value) { return value == null ? "" : value; }

    private String orderDate(String value) {
        if (value == null) return LocalDate.now(clock.withZone(SEOUL)).format(DateTimeFormatter.BASIC_ISO_DATE);
        try {
            if (!value.matches("[0-9]{8}")) throw new DateTimeParseException("Invalid date", value, 0);
            LocalDate.parse(value, DateTimeFormatter.BASIC_ISO_DATE);
            return value;
        } catch (DateTimeParseException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "주문 관찰 일자는 YYYYMMDD의 실제 날짜여야 합니다.");
        }
    }
}
