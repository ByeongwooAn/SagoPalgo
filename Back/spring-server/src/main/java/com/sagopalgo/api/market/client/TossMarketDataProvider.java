package com.sagopalgo.api.market.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Instant;
import java.util.Locale;
import java.util.Set;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * Toss 시세 API를 붙이기 위한 읽기 전용 Provider입니다.
 *
 * <p>공식 path가 확정되기 전까지 기본 설정은 비어 있으므로 자동으로 비활성화됩니다.</p>
 */
@Component
@Order(30)
public class TossMarketDataProvider implements MarketDataProvider {

    private static final String PROVIDER_CODE = "TOSS";
    private static final Set<String> SUPPORTED_MARKETS = Set.of("KOSPI", "KOSDAQ", "KONEX");

    private final Provider properties;
    private final RestClient restClient;

    public TossMarketDataProvider(SecuritiesProviderProperties securitiesProviderProperties, RestClient restClient) {
        this.properties = securitiesProviderProperties.getToss();
        this.restClient = restClient;
    }

    @Override
    public String providerCode() {
        return PROVIDER_CODE;
    }

    @Override
    public boolean supports(MarketDataRequest request) {
        return properties.isMarketDataEnabled()
            && properties.hasRequiredSecrets()
            && StringUtils.hasText(properties.getBaseUrl())
            && StringUtils.hasText(properties.getCurrentPricePath())
            && request != null
            && SUPPORTED_MARKETS.contains(normalizeMarket(request.market()))
            && StringUtils.hasText(request.stockCode());
    }

    @Override
    public StockQuote quote(MarketDataRequest request) {
        JsonNode response;
        try {
            response = restClient.get()
                .uri(currentPriceUri(request))
                .accept(MediaType.APPLICATION_JSON)
                .header("appkey", properties.getAppKey())
                .header("appsecret", properties.getAppSecret())
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 현재가 API 호출에 실패했습니다.");
        }

        String currentPrice = text(response, "currentPrice", "current_price", "price", "now_prc");
        if (!StringUtils.hasText(currentPrice)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 현재가 응답에 현재가가 없습니다.");
        }

        return new StockQuote(
            PROVIDER_CODE,
            request.stockCode(),
            text(response, "stockName", "stock_name", "name", "is_nm"),
            normalizeMarket(request.market()),
            decimal(currentPrice),
            decimal(text(response, "changePrice", "change_price", "bdy_cmpr")),
            decimal(text(response, "changeRate", "change_rate", "up_dwn_r_p2")),
            decimal(text(response, "volume", "tradingVolume", "acml_vlm")),
            decimal(text(response, "openPrice", "open_price", "opn_prc")),
            decimal(text(response, "highPrice", "high_price", "hgh_prc")),
            decimal(text(response, "lowPrice", "low_price", "lw_prc")),
            decimal(text(response, "previousClose", "previous_close", "bdy_cls_prc")),
            Instant.now()
        );
    }

    private URI currentPriceUri(MarketDataRequest request) {
        String normalizedPath = properties.getCurrentPricePath().startsWith("/")
            ? properties.getCurrentPricePath()
            : "/" + properties.getCurrentPricePath();
        return UriComponentsBuilder
            .fromUriString(properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath)
            .queryParam("stockCode", request.stockCode())
            .queryParam("market", normalizeMarket(request.market()))
            .build()
            .encode()
            .toUri();
    }

    private String text(JsonNode node, String... fieldNames) {
        if (node == null || node.isNull()) {
            return "";
        }
        for (String fieldName : fieldNames) {
            JsonNode found = find(node, fieldName);
            if (found != null && !found.isNull() && StringUtils.hasText(found.asText())) {
                return found.asText().trim();
            }
        }
        return "";
    }

    private JsonNode find(JsonNode node, String fieldName) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isObject()) {
            var names = node.fieldNames();
            while (names.hasNext()) {
                String name = names.next();
                if (name.equalsIgnoreCase(fieldName)) {
                    return node.get(name);
                }
            }
            var children = node.elements();
            while (children.hasNext()) {
                JsonNode found = find(children.next(), fieldName);
                if (found != null) {
                    return found;
                }
            }
        }
        if (node.isArray()) {
            var children = node.elements();
            while (children.hasNext()) {
                JsonNode found = find(children.next(), fieldName);
                if (found != null) {
                    return found;
                }
            }
        }
        return null;
    }

    private BigDecimal decimal(String value) {
        if (!StringUtils.hasText(value)) {
            return BigDecimal.ZERO;
        }
        try {
            return new BigDecimal(value.replace(",", "").replace("%", "").trim());
        } catch (NumberFormatException exception) {
            return BigDecimal.ZERO;
        }
    }

    private String normalizeMarket(String market) {
        return market == null ? "" : market.trim().toUpperCase(Locale.ROOT);
    }
}
