package com.sagopalgo.api.kb.client;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.market.model.CandleInterval;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

/**
 * KB증권 Open API의 인증, 계좌 목록, 보유 주식 조회를 담당합니다.
 */
@Component
public class KbSecuritiesAccountClient {

    private static final Duration TOKEN_REFRESH_MARGIN = Duration.ofMinutes(1);
    private static final int EXTERNAL_ERROR_BODY_LOG_LIMIT = 2_000;
    private static final Logger log = LoggerFactory.getLogger(KbSecuritiesAccountClient.class);
    private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

    private final Provider properties;
    private final RestClient restClient;
    private volatile AccessToken cachedAccessToken;

    public KbSecuritiesAccountClient(SecuritiesProviderProperties securitiesProviderProperties, RestClient restClient) {
        this.properties = securitiesProviderProperties.getKb();
        this.restClient = restClient;
    }

    public boolean isEnabled() {
        return properties.isAccountEnabled();
    }

    public boolean isMarketDataEnabled() {
        return properties.isMarketDataEnabled();
    }

    public void ensureAccountEnabled() {
        if (!properties.isAccountEnabled()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB증권 계좌 조회 설정이 꺼져 있습니다.");
        }
    }

    public String configuredAccountNumber() {
        return properties.getAccountNumber();
    }

    public String configuredAccountProductCode() {
        return properties.getAccountProductCode();
    }

    public boolean hasConfiguredAccountFallback() {
        return StringUtils.hasText(properties.getAccountNumber());
    }

    public boolean hasAccountsPath() {
        return StringUtils.hasText(properties.getAccountsPath());
    }

    public JsonNode fetchAccounts() {
        ensureAccountConfigured();
        ensurePathConfigured(properties.getAccountsPath(), "KB증권 계좌 목록 API 경로 설정이 필요합니다.");
        return post(properties.getAccountsPath(), properties.getAccountsTransactionId(), Map.of());
    }

    public JsonNode fetchHoldings() {
        ensureAccountConfigured();
        ensurePathConfigured(properties.getHoldingsPath(), "KB증권 보유 주식 API 경로 설정이 필요합니다.");
        ensureText(properties.getHoldingsInquiryClassification(), "KB증권 보유주식 조회구분 설정이 필요합니다.");
        ensureText(properties.getHoldingsMarketTimeCode(), "KB증권 보유주식 시장시간구분코드 설정이 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        dataBody.put("inq_clsf", properties.getHoldingsInquiryClassification());
        dataBody.put("mkt_tm_ccd", properties.getHoldingsMarketTimeCode());
        if (StringUtils.hasText(properties.getHoldingsStockCode())) {
            dataBody.put("is_no", properties.getHoldingsStockCode());
        }
        if (StringUtils.hasText(properties.getAccountNumber())) {
            dataBody.put(accountNumberField(), properties.getAccountNumber());
        }
        if (StringUtils.hasText(properties.getAccountProductCode())) {
            dataBody.put(accountProductCodeField(), properties.getAccountProductCode());
        }

        return post(properties.getHoldingsPath(), properties.getHoldingsTransactionId(), dataBody);
    }

    public JsonNode fetchSettlementBalance() {
        ensureAccountConfigured();
        ensurePathConfigured(properties.getSettlementBalancePath(), "KB증권 결제기준 잔고 현황 API 경로 설정이 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        if (StringUtils.hasText(properties.getBalanceInquiryClassification())) {
            dataBody.put("inq_clsf", properties.getBalanceInquiryClassification());
        }
        if (StringUtils.hasText(properties.getBalanceExchangeMarketPriceCode())) {
            dataBody.put("excg_mktpr_ccd", properties.getBalanceExchangeMarketPriceCode());
        }

        return post(properties.getSettlementBalancePath(), "", dataBody);
    }

    public JsonNode fetchExecutionBalance() {
        ensureAccountConfigured();
        ensurePathConfigured(properties.getExecutionBalancePath(), "KB증권 체결기준 잔고 현황 API 경로 설정이 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        if (StringUtils.hasText(properties.getBalanceExchangeMarketPriceCode())) {
            dataBody.put("excg_mktpr_ccd", properties.getBalanceExchangeMarketPriceCode());
        }

        return post(properties.getExecutionBalancePath(), "", dataBody);
    }

    public JsonNode fetchOrderExecutions(String orderDate, String executionClassification, String nextKey) {
        ensureAccountConfigured();
        Map<String, Object> dataBody = new LinkedHashMap<>();
        dataBody.put("ccls_clsf", executionClassification);
        dataBody.put("ordr_dt", orderDate);
        dataBody.put("nxt_key", nextKey);
        return post("/api/v1/ssqm2341", "", dataBody);
    }

    public JsonNode fetchCurrentPrice(String stockCode) {
        ensureMarketDataConfigured();
        ensurePathConfigured(properties.getCurrentPricePath(), "KB증권 현재가 API 경로 설정이 필요합니다.");
        ensureText(stockCode, "KB증권 현재가 조회 종목코드가 필요합니다.");
        ensureText(properties.getCurrentPriceExchangeClassification(), "KB증권 현재가 거래소구분 설정이 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        dataBody.put("excg_clsf", properties.getCurrentPriceExchangeClassification());
        dataBody.put("shrt_cd", stockCode.trim());

        return post(properties.getCurrentPricePath(), properties.getCurrentPriceTransactionId(), dataBody);
    }

    public JsonNode fetchCandles(String stockCode, String market, CandleInterval interval, int count) {
        ensureMarketDataConfigured();
        ensurePathConfigured(properties.getCandlePath(), "KB증권 통합차트 API 경로 설정이 필요합니다.");
        ensureText(stockCode, "KB증권 캔들 조회 종목코드가 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        dataBody.put("info_ccd", "2");
        dataBody.put("mkt_clsf", kbMarketCode(market));
        dataBody.put("chrt_clsf", kbCandleInterval(interval));
        dataBody.put("minute_tck_indx", "");
        dataBody.put("is_cd", stockCode.trim());
        dataBody.put("inq_clsf", "2");
        dataBody.put("strt_dy", "");
        dataBody.put("inq_cnt", Integer.toString(count));

        return post(properties.getCandlePath(), "", dataBody);
    }

    private String kbMarketCode(String market) {
        if ("KOSPI".equalsIgnoreCase(market)) {
            return "0";
        }
        if ("KOSDAQ".equalsIgnoreCase(market)) {
            return "1";
        }
        throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 통합차트가 지원하지 않는 시장입니다.");
    }

    private String kbCandleInterval(CandleInterval interval) {
        if (interval == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 주기가 필요합니다.");
        }
        return switch (interval) {
            case DAILY -> "D";
            case WEEKLY -> "W";
            case MONTHLY -> "M";
            case MINUTE -> throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                "KB증권 기간별 통합차트는 분봉을 지원하지 않습니다."
            );
        };
    }

    private JsonNode post(String path, String transactionId, Map<String, Object> dataBody) {
        try {
            JsonNode response = restClient.post()
                .uri(endpoint(path))
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .body(new KbApiRequest(dataHeader(transactionId), dataBody))
                .retrieve()
                .body(JsonNode.class);
            assertSuccessful(response);
            return response;
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 Open API 호출에 실패했습니다.");
        }
    }

    private String accessToken() {
        AccessToken accessToken = cachedAccessToken;
        if (isUsable(accessToken)) {
            return accessToken.value();
        }

        synchronized (this) {
            accessToken = cachedAccessToken;
            if (isUsable(accessToken)) {
                return accessToken.value();
            }
            cachedAccessToken = issueAccessToken();
            return cachedAccessToken.value();
        }
    }

    private AccessToken issueAccessToken() {
        ensureText(properties.getBaseUrl(), "KB증권 Open API Base URL 설정이 필요합니다.");
        ensureText(properties.getTokenPath(), "KB증권 토큰 API 경로 설정이 필요합니다.");
        String grantType = requiredTrimmedText(properties.getGrantType(), "KB증권 토큰 grant type 설정이 필요합니다.");
        String appKey = requiredTrimmedText(properties.getAppKey(), "KB증권 App Key 설정이 필요합니다.");
        String appSecret = requiredTrimmedText(properties.getAppSecret(), "KB증권 App Secret 설정이 필요합니다.");

        JsonNode response;
        try {
            response = restClient.post()
                .uri(endpoint(properties.getTokenPath()))
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(new KbTokenRequest(
                    tokenDataHeader(),
                    new KbTokenRequestBody(appKey, appSecret, grantType)
                ))
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientResponseException exception) {
            String responseBody = exception.getResponseBodyAsString();
            log.warn(
                "KB증권 access token 발급 실패. status={} body={}",
                exception.getStatusCode().value(),
                sanitizeExternalBody(responseBody)
            );
            throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                tokenFailureMessage(responseBody, exception.getStatusCode().value())
            );
        } catch (RestClientException exception) {
            log.warn("KB증권 access token 발급 HTTP 호출 실패: {}", exception.toString());
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 access token 발급에 실패했습니다.");
        }

        String accessToken = text(response, "access_token", "accessToken");
        if (!StringUtils.hasText(accessToken)) {
            log.warn("KB증권 access token 응답이 올바르지 않습니다. status=200 body={}", sanitizeExternalBody(response));
            throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                tokenInvalidResponseMessage(response)
            );
        }

        long expiresIn = tokenExpiresIn(response);
        return new AccessToken(accessToken, Instant.now().plusSeconds(expiresIn));
    }

    private long tokenExpiresIn(JsonNode response) {
        String expiresIn = text(response, "expires_in", "expiresIn");
        if (!StringUtils.hasText(expiresIn)) {
            return 3600;
        }
        try {
            long seconds = Long.parseLong(expiresIn.replace(",", "").trim());
            return seconds <= 0 ? 3600 : seconds;
        } catch (NumberFormatException exception) {
            return 3600;
        }
    }

    private Map<String, Object> tokenDataHeader() {
        Map<String, Object> dataHeader = new LinkedHashMap<>();
        dataHeader.put("ipAddr", "127.0.0.1");
        dataHeader.put("macAddr", "00:00:00:00:00:00");
        return dataHeader;
    }

    private String tokenFailureMessage(String responseBody, int statusCode) {
        String message = extractKbMessage(responseBody);
        if (StringUtils.hasText(message)) {
            return "KB증권 access token 발급 실패: " + message + " (status=" + statusCode + ")";
        }
        return "KB증권 access token 발급에 실패했습니다. (status=" + statusCode + ")";
    }

    private String tokenInvalidResponseMessage(JsonNode response) {
        String message = firstText(
            response,
            "processMessage",
            "msg1",
            "rsp_msg",
            "rspMessage",
            "message",
            "errMsg",
            "errorMessage"
        );
        if (StringUtils.hasText(message)) {
            return "KB증권 access token 응답 오류: " + message;
        }
        return "KB증권 access token 응답이 올바르지 않습니다.";
    }

    private String extractKbMessage(String responseBody) {
        if (!StringUtils.hasText(responseBody)) {
            return "";
        }
        try {
            JsonNode response = OBJECT_MAPPER.readTree(responseBody);
            return firstText(
                response,
                "processMessage",
                "msg1",
                "rsp_msg",
                "rspMessage",
                "message",
                "errMsg",
                "errorMessage"
            );
        } catch (JsonProcessingException exception) {
            return "";
        }
    }

    private Map<String, Object> dataHeader(String transactionId) {
        Map<String, Object> dataHeader = new LinkedHashMap<>();
        if (StringUtils.hasText(transactionId)) {
            dataHeader.put("tr_id", transactionId);
        }
        if (StringUtils.hasText(properties.getCustomerType())) {
            dataHeader.put("custtype", properties.getCustomerType());
        }
        return dataHeader;
    }

    private void assertSuccessful(JsonNode response) {
        if (response == null || response.isNull()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 Open API 응답이 비어 있습니다.");
        }

        String code = firstText(response, "rt_cd", "resultCode", "rsp_cd", "rspCode", "code", "errCode", "errorCode");
        String processFlag = firstText(response, "processFlag");
        if ((StringUtils.hasText(code) && !List.of("0", "0000", "200", "OK", "SUCCESS").contains(code.toUpperCase()))
            || "B".equalsIgnoreCase(processFlag)) {
            String message = firstText(
                response,
                "processMessage",
                "resultMessage",
                "msg1",
                "rsp_msg",
                "rspMessage",
                "message",
                "errMsg",
                "errorMessage"
            );
            if (!StringUtils.hasText(message)) {
                message = "KB증권 Open API가 실패 코드를 반환했습니다.";
            }
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 Open API 조회 실패: " + message);
        }
    }

    public List<JsonNode> items(JsonNode response, String... preferredArrayNames) {
        JsonNode body = child(response, "dataBody");
        JsonNode searchRoot = body == null ? response : body;
        List<JsonNode> preferred = findArrays(searchRoot, List.of(preferredArrayNames));
        if (containsArray(searchRoot, List.of(preferredArrayNames))) {
            return preferred;
        }
        if (!preferred.isEmpty()) {
            return preferred;
        }
        List<String> genericArrayNames = List.of("items", "list", "accounts", "accountList", "holdings", "holdingList", "output", "output1");
        List<JsonNode> generic = findArrays(searchRoot, genericArrayNames);
        if (containsArray(searchRoot, genericArrayNames)) {
            return generic;
        }
        if (!generic.isEmpty()) {
            return generic;
        }
        if (searchRoot != null && searchRoot.isObject()) {
            return List.of(searchRoot);
        }
        return List.of();
    }

    public String text(JsonNode node, String... fieldNames) {
        return firstText(node, fieldNames);
    }

    public BigDecimal decimal(JsonNode node, String... fieldNames) {
        String value = firstText(node, fieldNames);
        if (!StringUtils.hasText(value)) {
            return BigDecimal.ZERO;
        }
        try {
            return new BigDecimal(value.replace(",", "").replace("%", "").trim());
        } catch (NumberFormatException exception) {
            return BigDecimal.ZERO;
        }
    }

    private List<JsonNode> findArrays(JsonNode node, List<String> fieldNames) {
        List<JsonNode> found = new ArrayList<>();
        collectArrays(node, fieldNames, found);
        return found;
    }

    private boolean containsArray(JsonNode node, List<String> fieldNames) {
        if (node == null || node.isNull()) {
            return false;
        }
        if (node.isArray()) {
            return true;
        }
        if (!node.isObject()) {
            return false;
        }
        for (String fieldName : fieldNames) {
            JsonNode child = child(node, fieldName);
            if (child != null && child.isArray()) {
                return true;
            }
        }
        Iterator<JsonNode> children = node.elements();
        while (children.hasNext()) {
            if (containsArray(children.next(), fieldNames)) {
                return true;
            }
        }
        return false;
    }

    private void collectArrays(JsonNode node, List<String> fieldNames, List<JsonNode> found) {
        if (node == null || node.isNull()) {
            return;
        }
        if (node.isArray()) {
            node.forEach(found::add);
            return;
        }
        if (!node.isObject()) {
            return;
        }
        for (String fieldName : fieldNames) {
            JsonNode child = child(node, fieldName);
            if (child != null && child.isArray()) {
                child.forEach(found::add);
                return;
            }
        }
        Iterator<JsonNode> children = node.elements();
        while (children.hasNext()) {
            collectArrays(children.next(), fieldNames, found);
        }
    }

    private JsonNode child(JsonNode node, String fieldName) {
        if (node == null || !node.isObject()) {
            return null;
        }
        Iterator<String> names = node.fieldNames();
        while (names.hasNext()) {
            String name = names.next();
            if (name.equalsIgnoreCase(fieldName)) {
                return node.get(name);
            }
        }
        return null;
    }

    private String firstText(JsonNode node, String... fieldNames) {
        if (node == null || node.isNull()) {
            return "";
        }
        for (String fieldName : fieldNames) {
            JsonNode child = findTextNode(node, fieldName);
            if (child != null && !child.isNull()) {
                String value = child.asText();
                if (StringUtils.hasText(value)) {
                    return value.trim();
                }
            }
        }
        return "";
    }

    private JsonNode findTextNode(JsonNode node, String fieldName) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isObject()) {
            Iterator<String> names = node.fieldNames();
            while (names.hasNext()) {
                String name = names.next();
                if (name.equalsIgnoreCase(fieldName)) {
                    return node.get(name);
                }
            }
            Iterator<JsonNode> children = node.elements();
            while (children.hasNext()) {
                JsonNode found = findTextNode(children.next(), fieldName);
                if (found != null) {
                    return found;
                }
            }
        }
        if (node.isArray()) {
            Iterator<JsonNode> children = node.elements();
            while (children.hasNext()) {
                JsonNode found = findTextNode(children.next(), fieldName);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    private URI endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return URI.create(properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath);
    }

    private void ensureAccountConfigured() {
        ensureAccountEnabled();
        ensureText(properties.getAppKey(), "KB증권 App Key 설정이 필요합니다.");
        ensureText(properties.getAppSecret(), "KB증권 App Secret 설정이 필요합니다.");
    }

    private void ensureMarketDataConfigured() {
        if (!properties.isMarketDataEnabled()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB증권 시세 조회 설정이 꺼져 있습니다.");
        }
        ensureText(properties.getAppKey(), "KB증권 App Key 설정이 필요합니다.");
        ensureText(properties.getAppSecret(), "KB증권 App Secret 설정이 필요합니다.");
    }

    private void ensurePathConfigured(String path, String message) {
        ensureText(path, message);
    }

    private void ensureText(String value, String message) {
        if (!StringUtils.hasText(value)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
    }

    private String requiredTrimmedText(String value, String message) {
        ensureText(value, message);
        return value.trim();
    }

    private boolean isUsable(AccessToken accessToken) {
        return accessToken != null
            && StringUtils.hasText(accessToken.value())
            && accessToken.expiresAt().isAfter(Instant.now().plus(TOKEN_REFRESH_MARGIN));
    }

    private String sanitizeExternalBody(JsonNode body) {
        return body == null ? "" : sanitizeExternalBody(body.toString());
    }

    private String sanitizeExternalBody(String body) {
        if (!StringUtils.hasText(body)) {
            return "";
        }

        String sanitized = body
            .replaceAll("(?i)(\"?(?:appKey|appSecret|access_token|accessToken|token|authorization)\"?\\s*[:=]\\s*\")([^\"]+)(\")", "$1***$3")
            .replaceAll("(?i)(Bearer\\s+)[A-Za-z0-9._~+/-]+=*", "$1***");
        if (sanitized.length() <= EXTERNAL_ERROR_BODY_LOG_LIMIT) {
            return sanitized;
        }
        return sanitized.substring(0, EXTERNAL_ERROR_BODY_LOG_LIMIT) + "...(truncated)";
    }

    private String accountNumberField() {
        return StringUtils.hasText(properties.getAccountNumberField()) ? properties.getAccountNumberField() : "accountNumber";
    }

    private String accountProductCodeField() {
        return StringUtils.hasText(properties.getAccountProductCodeField())
            ? properties.getAccountProductCodeField()
            : "accountProductCode";
    }

    private record AccessToken(String value, Instant expiresAt) {
    }

    private record KbTokenRequest(
        Map<String, Object> dataHeader,
        KbTokenRequestBody dataBody
    ) {
    }

    private record KbTokenRequestBody(
        String appKey,
        String appSecret,
        String grantType
    ) {
    }

    private record KbApiRequest(
        Map<String, Object> dataHeader,
        Map<String, Object> dataBody
    ) {
    }
}
