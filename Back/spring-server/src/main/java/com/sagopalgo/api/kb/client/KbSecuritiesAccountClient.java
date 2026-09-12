package com.sagopalgo.api.kb.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;

/**
 * KB증권 Open API의 인증, 계좌 목록, 보유 주식 조회를 담당합니다.
 */
@Component
public class KbSecuritiesAccountClient {

    private static final Duration TOKEN_REFRESH_MARGIN = Duration.ofMinutes(1);

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
        ensureText(properties.getAccountNumber(), "KB증권 계좌번호 설정이 필요합니다.");

        Map<String, Object> dataBody = new LinkedHashMap<>();
        dataBody.put(accountNumberField(), properties.getAccountNumber());
        if (StringUtils.hasText(properties.getAccountProductCode())) {
            dataBody.put(accountProductCodeField(), properties.getAccountProductCode());
        }

        return post(properties.getHoldingsPath(), properties.getHoldingsTransactionId(), dataBody);
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
        ensureText(properties.getGrantType(), "KB증권 토큰 grant type 설정이 필요합니다.");
        ensureText(properties.getAppKey(), "KB증권 App Key 설정이 필요합니다.");
        ensureText(properties.getAppSecret(), "KB증권 App Secret 설정이 필요합니다.");

        KbTokenResponse response;
        try {
            response = restClient.post()
                .uri(endpoint(properties.getTokenPath()))
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(new KbTokenRequest(properties.getGrantType(), properties.getAppKey(), properties.getAppSecret()))
                .retrieve()
                .body(KbTokenResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 access token 발급에 실패했습니다.");
        }

        if (response == null || !StringUtils.hasText(response.accessToken())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 access token 응답이 올바르지 않습니다.");
        }

        long expiresIn = response.expiresIn() == null || response.expiresIn() <= 0 ? 3600 : response.expiresIn();
        return new AccessToken(response.accessToken(), Instant.now().plusSeconds(expiresIn));
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

        String code = firstText(response, "rt_cd", "rsp_cd", "rspCode", "code", "errCode", "errorCode");
        if (StringUtils.hasText(code) && !List.of("0", "0000", "OK", "SUCCESS").contains(code.toUpperCase())) {
            String message = firstText(response, "msg1", "rsp_msg", "rspMessage", "message", "errMsg", "errorMessage");
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
        if (!preferred.isEmpty()) {
            return preferred;
        }
        List<JsonNode> generic = findArrays(searchRoot, List.of("items", "list", "accounts", "accountList", "holdings", "holdingList", "output", "output1"));
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

    private void ensurePathConfigured(String path, String message) {
        ensureText(path, message);
    }

    private void ensureText(String value, String message) {
        if (!StringUtils.hasText(value)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
    }

    private boolean isUsable(AccessToken accessToken) {
        return accessToken != null
            && StringUtils.hasText(accessToken.value())
            && accessToken.expiresAt().isAfter(Instant.now().plus(TOKEN_REFRESH_MARGIN));
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
        @JsonProperty("grant_type")
        String grantType,
        String appKey,
        String appSecret
    ) {
    }

    private record KbTokenResponse(
        @JsonProperty("access_token")
        String accessToken,

        @JsonProperty("expires_in")
        Long expiresIn
    ) {
    }

    private record KbApiRequest(
        Map<String, Object> dataHeader,
        Map<String, Object> dataBody
    ) {
    }
}
