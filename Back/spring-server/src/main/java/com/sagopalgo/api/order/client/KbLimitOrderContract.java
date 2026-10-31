package com.sagopalgo.api.order.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.Map;

/** KB 국내주식 정규장 지정가 주문의 문서화된 요청·응답 형식만 다룹니다. 네트워크 호출은 하지 않습니다. */
public final class KbLimitOrderContract {
    public static final String BUY_PATH = "/api/v1/ssam1802";
    public static final String SELL_PATH = "/api/v1/ssam1801";
    private static final String INVALID_ORDER_MESSAGE =
        "KB 지정가 주문은 KOSPI/KOSDAQ 6자리 종목코드, 9자리 이하 정수 원화 지정가와 10자리 이하 정수 주식 수량만 지원합니다.";

    private KbLimitOrderContract() {
    }

    public static boolean isSupported(OrderPrecheckRequest request) {
        if (request == null || request.stockCode() == null || request.market() == null
            || request.side() == null || request.limitPrice() == null || request.quantity() == null) {
            return false;
        }
        String market = request.market().trim().toUpperCase(java.util.Locale.ROOT);
        String side = request.side().trim().toUpperCase(java.util.Locale.ROOT);
        return request.stockCode().trim().matches("[0-9]{6}")
            && ("KOSPI".equals(market) || "KOSDAQ".equals(market))
            && ("BUY".equals(side) || "SELL".equals(side))
            && wholePositiveWithinDigits(request.limitPrice(), 9)
            && wholePositiveWithinDigits(request.quantity(), 10);
    }

    public static void requireSupported(OrderPrecheckRequest request) {
        if (!isSupported(request)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, INVALID_ORDER_MESSAGE);
        }
    }

    public static Request encode(OrderPrecheckRequest request) {
        requireSupported(request);
        Map<String, String> dataBody = new LinkedHashMap<>();
        dataBody.put("mkt_tm_clsf", "1");
        dataBody.put("is_cd", request.stockCode().trim());
        dataBody.put("ordr_q", request.quantity().toBigIntegerExact().toString());
        dataBody.put("ordr_uprc", request.limitPrice().toBigIntegerExact().toString());
        dataBody.put("ordr_ccd", "00");
        dataBody.put("sor_ordr_ccd", "K");
        String path = "BUY".equalsIgnoreCase(request.side().trim()) ? BUY_PATH : SELL_PATH;
        return new Request(path, Map.copyOf(dataBody));
    }

    public static Outcome interpret(JsonNode response) {
        JsonNode header = response == null ? null : response.path("dataHeader");
        JsonNode body = response == null ? null : response.path("dataBody");
        String resultCode = value(header, "resultCode");
        String processFlag = value(header, "processFlag");
        String processCode = value(header, "processCode");
        String orderNumber = value(body, "ordr_no");
        String message = value(body, "o_msg");
        if (message.isEmpty()) {
            message = value(header, "processMessage");
        }
        boolean hasOrderNumber = !orderNumber.isEmpty() && !orderNumber.matches("0+");
        boolean validOrderNumber = orderNumber.matches("[0-9]{10}") && hasOrderNumber;
        if ("200".equals(resultCode) && "B".equalsIgnoreCase(processFlag)) {
            return new Outcome(hasOrderNumber ? Status.UNKNOWN : Status.REJECTED, "", resultCode, processCode, message);
        }
        if ("200".equals(resultCode) && "A".equalsIgnoreCase(processFlag)
            && validOrderNumber) {
            return new Outcome(Status.ACCEPTED, orderNumber, resultCode, processCode, message);
        }
        return new Outcome(Status.UNKNOWN, "", resultCode, processCode, message);
    }

    private static boolean wholePositiveWithinDigits(BigDecimal value, int maxDigits) {
        BigDecimal normalized = value.stripTrailingZeros();
        return value.signum() > 0
            && normalized.scale() <= 0
            && (long) normalized.precision() - normalized.scale() <= maxDigits;
    }

    private static String value(JsonNode node, String field) {
        if (node == null || node.isMissingNode() || node.isNull()) {
            return "";
        }
        JsonNode child = node.path(field);
        return child.isMissingNode() || child.isNull() ? "" : child.asText().trim();
    }

    public record Request(String path, Map<String, String> dataBody) {
    }

    public record Outcome(Status status, String orderNumber, String resultCode, String processCode, String message) {
    }

    public enum Status {
        ACCEPTED,
        REJECTED,
        UNKNOWN
    }
}
