package com.sagopalgo.api.market.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockInfo;
import com.sagopalgo.api.market.model.DomesticStockIdentity;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * 토스증권 Open API의 시세와 종목 정보를 내부 표준 모델로 변환합니다.
 */
@Component
@Order(30)
public class TossMarketDataProvider implements MarketDataProvider {

    private static final String PROVIDER_CODE = "TOSS";
    private static final Duration TOKEN_REFRESH_MARGIN = Duration.ofMinutes(1);
    private static final Set<String> SUPPORTED_MARKETS = Set.of(
        "KOSPI", "KOSDAQ", "KONEX", "KR_ETC",
        "NYSE", "NASDAQ", "AMEX", "US_ETC"
    );

    private final Provider properties;
    private final RestClient restClient;
    private volatile AccessToken cachedAccessToken;

    public TossMarketDataProvider(
        SecuritiesProviderProperties securitiesProviderProperties,
        RestClient restClient
    ) {
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
            && StringUtils.hasText(properties.getTokenPath())
            && StringUtils.hasText(properties.getCurrentPricePath())
            && request != null
            && SUPPORTED_MARKETS.contains(normalizeMarket(request.market()))
            && StringUtils.hasText(request.stockCode());
    }

    @Override
    public StockQuote quote(MarketDataRequest request) {
        ensureQuoteConfigured();
        PriceEnvelope response;
        try {
            response = restClient.get()
                .uri(symbolsUri(properties.getCurrentPricePath(), request.stockCode()))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .retrieve()
                .body(PriceEnvelope.class);
        } catch (RestClientException exception) {
            throw externalError("토스증권 현재가 API 호출에 실패했습니다.");
        }

        PriceItem item = findBySymbol(response == null ? null : response.result(), request.stockCode())
            .orElseThrow(() -> new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                "토스증권 현재가 응답에 요청 종목이 없습니다."
            ));

        return new StockQuote(
            PROVIDER_CODE,
            item.symbol(),
            "",
            normalizeMarket(request.market()),
            requiredDecimal(item.lastPrice(), "토스증권 현재가 형식이 올바르지 않습니다."),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            parseInstant(item.timestamp())
        );
    }

    @Override
    public List<StockCandle> candles(
        MarketDataRequest request,
        CandleInterval interval,
        int count
    ) {
        String intervalCode = intervalCode(interval);
        if (intervalCode == null) {
            return List.of();
        }
        ensureCandleConfigured();

        CandleEnvelope response;
        try {
            response = restClient.get()
                .uri(candleUri(request.stockCode(), intervalCode, count))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .retrieve()
                .body(CandleEnvelope.class);
        } catch (RestClientException exception) {
            throw externalError("토스증권 캔들 API 호출에 실패했습니다.");
        }

        if (response == null || response.result() == null || response.result().candles() == null) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 캔들 응답이 비어 있습니다.");
        }
        return response.result().candles().stream()
            .map(item -> toCandle(request, interval, item))
            .sorted(Comparator.comparing(StockCandle::dateTime))
            .toList();
    }

    @Override
    public Optional<StockInfo> stockInfo(MarketDataRequest request) {
        ensureStockInfoConfigured();
        StockInfoEnvelope response;
        try {
            response = restClient.get()
                .uri(symbolsUri(properties.getStockInfoPath(), request.stockCode()))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .retrieve()
                .body(StockInfoEnvelope.class);
        } catch (RestClientException exception) {
            throw externalError("토스증권 종목 정보 API 호출에 실패했습니다.");
        }

        return findStockInfo(response == null ? null : response.result(), request.stockCode())
            .map(this::toStockInfo);
    }

    @Override
    public Optional<DomesticStockIdentity> domesticStockIdentity(String stockCode) {
        MarketDataRequest request = new MarketDataRequest(stockCode, "KOSPI");
        if (!supports(request) || !StringUtils.hasText(properties.getStockInfoPath())) return Optional.empty();
        // KOSPI는 호출 가능 여부 점검용이며 반환 시장은 종목정보 응답에서만 가져옵니다.
        return stockInfo(request).map(info -> new DomesticStockIdentity(
            info.provider(), info.stockCode(), info.stockName(), normalizeMarket(info.market())));
    }

    private String accessToken() {
        AccessToken token = cachedAccessToken;
        if (isUsable(token)) {
            return token.value();
        }

        synchronized (this) {
            token = cachedAccessToken;
            if (isUsable(token)) {
                return token.value();
            }
            cachedAccessToken = issueAccessToken();
            return cachedAccessToken.value();
        }
    }

    private AccessToken issueAccessToken() {
        var form = new LinkedMultiValueMap<String, String>();
        form.add("grant_type", properties.getGrantType());
        form.add("client_id", properties.getAppKey());
        form.add("client_secret", properties.getAppSecret());

        TokenResponse response;
        try {
            response = restClient.post()
                .uri(endpoint(properties.getTokenPath()))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .body(form)
                .retrieve()
                .body(TokenResponse.class);
        } catch (RestClientException exception) {
            throw externalError("토스증권 access token 발급에 실패했습니다.");
        }

        if (response == null || !StringUtils.hasText(response.accessToken())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 access token 응답이 올바르지 않습니다.");
        }
        long expiresIn = response.expiresIn() == null || response.expiresIn() <= 0
            ? Duration.ofHours(1).toSeconds()
            : response.expiresIn();
        return new AccessToken(response.accessToken(), Instant.now().plusSeconds(expiresIn));
    }

    private StockCandle toCandle(
        MarketDataRequest request,
        CandleInterval interval,
        CandleItem item
    ) {
        LocalDateTime dateTime;
        try {
            dateTime = OffsetDateTime.parse(item.timestamp()).toLocalDateTime();
        } catch (DateTimeParseException | NullPointerException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 캔들 시각 형식이 올바르지 않습니다.");
        }
        return new StockCandle(
            PROVIDER_CODE,
            request.stockCode(),
            normalizeMarket(request.market()),
            dateTime,
            interval,
            requiredDecimal(item.openPrice(), "토스증권 캔들 시가 형식이 올바르지 않습니다."),
            requiredDecimal(item.highPrice(), "토스증권 캔들 고가 형식이 올바르지 않습니다."),
            requiredDecimal(item.lowPrice(), "토스증권 캔들 저가 형식이 올바르지 않습니다."),
            requiredDecimal(item.closePrice(), "토스증권 캔들 종가 형식이 올바르지 않습니다."),
            requiredDecimal(item.volume(), "토스증권 캔들 거래량 형식이 올바르지 않습니다.")
        );
    }

    private StockInfo toStockInfo(StockInfoItem item) {
        KoreanMarketDetail detail = item.koreanMarketDetail();
        return new StockInfo(
            PROVIDER_CODE,
            item.symbol(),
            item.name(),
            item.englishName(),
            item.market(),
            item.securityType(),
            Boolean.TRUE.equals(item.commonShare()),
            item.status(),
            item.currency(),
            parseDate(item.listDate()),
            parseDate(item.delistDate()),
            decimal(item.sharesOutstanding()),
            detail != null && Boolean.TRUE.equals(detail.nxtSupported()),
            detail != null && (
                Boolean.TRUE.equals(detail.krxTradingSuspended())
                    || Boolean.TRUE.equals(detail.nxtTradingSuspended())
            )
        );
    }

    private Optional<PriceItem> findBySymbol(List<PriceItem> items, String stockCode) {
        if (items == null) {
            return Optional.empty();
        }
        return items.stream()
            .filter(item -> item != null && stockCode.equalsIgnoreCase(item.symbol()))
            .findFirst();
    }

    private Optional<StockInfoItem> findStockInfo(List<StockInfoItem> items, String stockCode) {
        if (items == null) {
            return Optional.empty();
        }
        return items.stream()
            .filter(item -> item != null && stockCode.equalsIgnoreCase(item.symbol()))
            .findFirst();
    }

    private URI symbolsUri(String path, String stockCode) {
        return UriComponentsBuilder.fromUri(endpoint(path))
            .queryParam("symbols", stockCode)
            .build()
            .encode()
            .toUri();
    }

    private URI candleUri(String stockCode, String interval, int count) {
        return UriComponentsBuilder.fromUri(endpoint(properties.getCandlePath()))
            .queryParam("symbol", stockCode)
            .queryParam("interval", interval)
            .queryParam("count", Math.max(1, Math.min(count, 200)))
            .queryParam("adjusted", true)
            .build()
            .encode()
            .toUri();
    }

    private URI endpoint(String path) {
        String normalizedPath = path.startsWith("/") ? path : "/" + path;
        return URI.create(properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath);
    }

    private String intervalCode(CandleInterval interval) {
        if (interval == CandleInterval.DAILY) {
            return "1d";
        }
        if (interval == CandleInterval.MINUTE) {
            return "1m";
        }
        return null;
    }

    private String normalizeMarket(String market) {
        return market == null ? "" : market.trim().toUpperCase(Locale.ROOT);
    }

    private Instant parseInstant(String value) {
        if (!StringUtils.hasText(value)) {
            return Instant.now();
        }
        try {
            return OffsetDateTime.parse(value).toInstant();
        } catch (DateTimeParseException exception) {
            return Instant.now();
        }
    }

    private LocalDate parseDate(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            return LocalDate.parse(value);
        } catch (DateTimeParseException exception) {
            return null;
        }
    }

    private BigDecimal requiredDecimal(String value, String message) {
        if (!StringUtils.hasText(value)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
        try {
            return new BigDecimal(value.replace(",", "").trim());
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
    }

    private BigDecimal decimal(String value) {
        if (!StringUtils.hasText(value)) {
            return BigDecimal.ZERO;
        }
        try {
            return new BigDecimal(value.replace(",", "").trim());
        } catch (NumberFormatException exception) {
            return BigDecimal.ZERO;
        }
    }

    private boolean isUsable(AccessToken token) {
        return token != null
            && StringUtils.hasText(token.value())
            && token.expiresAt().isAfter(Instant.now().plus(TOKEN_REFRESH_MARGIN));
    }

    private void ensureQuoteConfigured() {
        ensureCommonConfigured();
        if (!StringUtils.hasText(properties.getCurrentPricePath())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 현재가 API 설정이 필요합니다.");
        }
    }

    private void ensureCandleConfigured() {
        ensureCommonConfigured();
        if (!StringUtils.hasText(properties.getCandlePath())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 캔들 API 설정이 필요합니다.");
        }
    }

    private void ensureStockInfoConfigured() {
        ensureCommonConfigured();
        if (!StringUtils.hasText(properties.getStockInfoPath())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 종목 정보 API 설정이 필요합니다.");
        }
    }

    private void ensureCommonConfigured() {
        if (!StringUtils.hasText(properties.getBaseUrl())
            || !StringUtils.hasText(properties.getGrantType())
            || !StringUtils.hasText(properties.getTokenPath())
            || !properties.hasRequiredSecrets()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "토스증권 Open API 설정이 필요합니다.");
        }
    }

    private ApiException externalError(String message) {
        return new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
    }

    private record AccessToken(String value, Instant expiresAt) {
    }

    private record TokenResponse(
        @JsonProperty("access_token") String accessToken,
        @JsonProperty("token_type") String tokenType,
        @JsonProperty("expires_in") Long expiresIn
    ) {
    }

    private record PriceEnvelope(List<PriceItem> result) {
    }

    private record PriceItem(
        String symbol,
        String timestamp,
        String lastPrice,
        String currency
    ) {
    }

    private record CandleEnvelope(CandlePage result) {
    }

    private record CandlePage(List<CandleItem> candles, String nextBefore) {
    }

    private record CandleItem(
        String timestamp,
        String openPrice,
        String highPrice,
        String lowPrice,
        String closePrice,
        String volume,
        String currency
    ) {
    }

    private record StockInfoEnvelope(List<StockInfoItem> result) {
    }

    private record StockInfoItem(
        String symbol,
        String name,
        String englishName,
        String market,
        String securityType,
        @JsonProperty("isCommonShare") Boolean commonShare,
        String status,
        String currency,
        String listDate,
        String delistDate,
        String sharesOutstanding,
        KoreanMarketDetail koreanMarketDetail
    ) {
    }

    private record KoreanMarketDetail(
        Boolean nxtSupported,
        Boolean krxTradingSuspended,
        Boolean nxtTradingSuspended
    ) {
    }
}
