package com.sagopalgo.api.market.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Set;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * 한국투자증권 Open API로 국내 주식 현재가를 조회하는 클라이언트입니다.
 */
@Component
public class KisMarketPriceClient implements MarketPriceClient {

    private static final Set<String> SUPPORTED_MARKETS = Set.of("KOSPI", "KOSDAQ", "KONEX");
    private static final String DOMESTIC_STOCK_MARKET_DIVISION = "J";
    private static final Duration TOKEN_REFRESH_MARGIN = Duration.ofMinutes(1);
    private static final DateTimeFormatter KIS_TOKEN_EXPIRATION_FORMAT =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final KisMarketProperties properties;
    private final RestClient restClient;
    private volatile AccessToken cachedAccessToken;

    public KisMarketPriceClient(KisMarketProperties properties, RestClient restClient) {
        this.properties = properties;
        this.restClient = restClient;
    }

    @Override
    public boolean supports(Holding holding) {
        return properties.isEnabled()
            && holding != null
            && SUPPORTED_MARKETS.contains(normalizeMarket(holding.getMarket()))
            && StringUtils.hasText(holding.getStockCode());
    }

    @Override
    public BigDecimal currentPrice(Holding holding) {
        ensureConfigured();

        KisPriceResponse response;
        try {
            response = restClient.get()
                .uri(priceUri(holding.getStockCode()))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .header("appkey", properties.getAppKey())
                .header("appsecret", properties.getAppSecret())
                .header("tr_id", properties.getTransactionId())
                .header("custtype", properties.getCustomerType())
                .retrieve()
                .body(KisPriceResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 API 호출에 실패했습니다.");
        }

        return parseCurrentPrice(response);
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
        KisTokenResponse response;
        try {
            response = restClient.post()
                .uri(endpoint(properties.getTokenPath()))
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .body(new KisTokenRequest(properties.getGrantType(), properties.getAppKey(), properties.getAppSecret()))
                .retrieve()
                .body(KisTokenResponse.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 access token 발급에 실패했습니다.");
        }

        if (response == null || !StringUtils.hasText(response.accessToken())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 access token 응답이 올바르지 않습니다.");
        }

        return new AccessToken(response.accessToken(), tokenExpiresAt(response));
    }

    private BigDecimal parseCurrentPrice(KisPriceResponse response) {
        if (response == null) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 응답이 비어 있습니다.");
        }
        if (StringUtils.hasText(response.resultCode()) && !"0".equals(response.resultCode())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, failureMessage(response));
        }
        if (response.output() == null || !StringUtils.hasText(response.output().currentPrice())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 응답에 현재가가 없습니다.");
        }

        try {
            return new BigDecimal(response.output().currentPrice().replace(",", "").trim());
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 형식이 올바르지 않습니다.");
        }
    }

    private String failureMessage(KisPriceResponse response) {
        if (StringUtils.hasText(response.message())) {
            return "한국투자증권 현재가 조회 실패: " + response.message();
        }
        return "한국투자증권 현재가 조회에 실패했습니다.";
    }

    private Instant tokenExpiresAt(KisTokenResponse response) {
        if (response.expiresIn() != null && response.expiresIn() > 0) {
            return Instant.now().plusSeconds(response.expiresIn());
        }
        if (StringUtils.hasText(response.accessTokenExpiredAt())) {
            try {
                return LocalDateTime.parse(response.accessTokenExpiredAt(), KIS_TOKEN_EXPIRATION_FORMAT)
                    .atZone(ZoneId.of("Asia/Seoul"))
                    .toInstant();
            } catch (DateTimeParseException ignored) {
                return Instant.now().plus(Duration.ofHours(1));
            }
        }
        return Instant.now().plus(Duration.ofHours(1));
    }

    private boolean isUsable(AccessToken accessToken) {
        return accessToken != null
            && StringUtils.hasText(accessToken.value())
            && accessToken.expiresAt().isAfter(Instant.now().plus(TOKEN_REFRESH_MARGIN));
    }

    private URI priceUri(String stockCode) {
        return UriComponentsBuilder
            .fromUri(endpoint(properties.getPricePath()))
            .queryParam("FID_COND_MRKT_DIV_CODE", DOMESTIC_STOCK_MARKET_DIVISION)
            .queryParam("FID_INPUT_ISCD", stockCode)
            .build()
            .encode()
            .toUri();
    }

    private URI endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return URI.create(properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath);
    }

    private void ensureConfigured() {
        if (!StringUtils.hasText(properties.getBaseUrl())
            || !StringUtils.hasText(properties.getAppKey())
            || !StringUtils.hasText(properties.getAppSecret())
            || !StringUtils.hasText(properties.getTransactionId())
            || !StringUtils.hasText(properties.getCustomerType())
            || !StringUtils.hasText(properties.getTokenPath())
            || !StringUtils.hasText(properties.getPricePath())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 시세 API 설정이 필요합니다.");
        }
    }

    private String normalizeMarket(String market) {
        return market == null ? "" : market.trim().toUpperCase(Locale.ROOT);
    }

    private record AccessToken(String value, Instant expiresAt) {
    }

    private record KisTokenRequest(
        @JsonProperty("grant_type")
        String grantType,
        String appkey,
        String appsecret
    ) {
    }

    private record KisTokenResponse(
        @JsonProperty("access_token")
        String accessToken,

        @JsonProperty("expires_in")
        Long expiresIn,

        @JsonProperty("access_token_token_expired")
        String accessTokenExpiredAt
    ) {
    }

    private record KisPriceResponse(
        @JsonProperty("rt_cd")
        String resultCode,

        @JsonProperty("msg1")
        String message,

        Output output
    ) {
    }

    private record Output(
        @JsonProperty("stck_prpr")
        String currentPrice
    ) {
    }
}
