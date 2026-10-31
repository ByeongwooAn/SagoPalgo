package com.sagopalgo.api.market.client;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.market.model.MarketIndexSnapshot;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.KisMarketProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.net.URI;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.LocalDate;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Locale;
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * 한국투자증권 Open API로 국내 주식 현재가를 조회하는 클라이언트입니다.
 */
@Component
@Order(20)
public class KisMarketPriceClient implements MarketDataProvider {

    private static final Logger log = LoggerFactory.getLogger(KisMarketPriceClient.class);

    private volatile MarketIndexSnapshot cachedIndex;
    private volatile Instant indexCheckedAt;

    /** 공식 업종기간별시세 U/0001/D 계약. 호출 제한을 위해 성공/실패 모두 1분 캐시합니다. */
    public synchronized MarketIndexSnapshot kospi() {
        Instant now = Instant.now();
        if (cachedIndex != null && indexCheckedAt != null && now.isBefore(indexCheckedAt.plusSeconds(60))) {
            return cachedIndex;
        }
        try {
            if (!properties.isEnabled() || !StringUtils.hasText(properties.getAppKey())
                || !StringUtils.hasText(properties.getAppSecret())) {
                cachedIndex = new MarketIndexSnapshot("DISABLED", "KIS", "KIS 활성화와 인증 설정을 확인하세요.",
                    null, null, null, List.of());
            } else {
                cachedIndex = fetchKospi();
            }
        } catch (ApiException | RestClientException | IllegalArgumentException exception) {
            String diagnostic = exception instanceof RestClientException restException
                ? KisApiErrors.requestFailure("INDEX", "코스피", restException).getMessage()
                : exception instanceof ApiException ? exception.getMessage() : "코스피 응답 형식 오류 [stage=INDEX kind=INVALID_RESPONSE]";
            log.warn("KIS 코스피 조회 실패. message={}", diagnostic);
            // 이전 성공값을 새 시세로 가장하지 않습니다. 오류 원문/인증값도 응답에 넣지 않습니다.
            cachedIndex = new MarketIndexSnapshot("FAILED", "KIS", "코스피 조회에 실패했습니다. KIS 설정·조회 권한을 확인하세요.",
                null, null, null, List.of());
        }
        indexCheckedAt = now;
        return cachedIndex;
    }

    private MarketIndexSnapshot fetchKospi() {
        LocalDate today = LocalDate.now(ZoneId.of("Asia/Seoul"));
        URI uri = UriComponentsBuilder.fromUri(endpoint(properties.getIndexPath()))
            .queryParam("FID_COND_MRKT_DIV_CODE", "U")
            .queryParam("FID_INPUT_ISCD", "0001")
            .queryParam("FID_INPUT_DATE_1", today.minusDays(45).format(DateTimeFormatter.BASIC_ISO_DATE))
            .queryParam("FID_INPUT_DATE_2", today.format(DateTimeFormatter.BASIC_ISO_DATE))
            .queryParam("FID_PERIOD_DIV_CODE", "D").build().encode().toUri();
        JsonNode body = restClient.get().uri(uri).accept(MediaType.APPLICATION_JSON)
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
            .header("appkey", properties.getAppKey()).header("appsecret", properties.getAppSecret())
            .header("tr_id", properties.getIndexTransactionId()).header("custtype", properties.getCustomerType())
            .retrieve().body(JsonNode.class);
        if (body != null && !"0".equals(body.path("rt_cd").asText())) {
            throw KisApiErrors.responseFailure("INDEX", "코스피", body.path("rt_cd").asText(), body.path("msg_cd").asText());
        }
        if (body == null || !body.path("output2").isArray()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "코스피 응답이 올바르지 않습니다.");
        }
        JsonNode summary = body.path("output1");
        if (!summary.path("bstp_cls_code").asText().isBlank()
            && !"0001".equals(summary.path("bstp_cls_code").asText())) {
            throw new IllegalArgumentException("Unexpected index code");
        }
        BigDecimal value = indexNumber(summary, "bstp_nmix_prpr");
        BigDecimal rate = indexNumber(summary, "bstp_nmix_prdy_ctrt");
        if (value.signum() <= 0) throw new IllegalArgumentException("Invalid index value");
        java.util.Map<LocalDate, BigDecimal> unique = new java.util.TreeMap<>();
        for (JsonNode item : body.path("output2")) {
            try {
                LocalDate date = LocalDate.parse(item.path("stck_bsop_date").asText(), DateTimeFormatter.BASIC_ISO_DATE);
                BigDecimal close = indexNumber(item, "bstp_nmix_prpr");
                if (!date.isAfter(today) && close.signum() > 0) unique.put(date, close);
            } catch (IllegalArgumentException | DateTimeParseException ignored) {
                // 빈 날짜/잘못된 행을 0원 지수로 만들지 않습니다.
            }
        }
        List<MarketIndexSnapshot.Point> points = unique.entrySet().stream()
            .map(item -> new MarketIndexSnapshot.Point(item.getKey(), item.getValue())).toList();
        if (points.isEmpty()) throw new IllegalArgumentException("Empty index history");
        if (points.size() > 20) points = points.subList(points.size() - 20, points.size());
        return new MarketIndexSnapshot("SUCCESS", "KIS", "KOSPI · 최근 최대 20거래일 일봉", value, rate, Instant.now(), points);
    }

    private BigDecimal indexNumber(JsonNode node, String field) {
        String value = node.path(field).asText().trim().replace(",", "");
        if (value.isEmpty()) throw new IllegalArgumentException("Missing index number");
        return new BigDecimal(value);
    }

    private static final String PROVIDER_CODE = "KIS";
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

    public boolean supports(Holding holding) {
        return supports(MarketDataRequest.from(holding));
    }

    @Override
    public String providerCode() {
        return PROVIDER_CODE;
    }

    @Override
    public boolean supports(MarketDataRequest request) {
        return properties.isEnabled()
            && request != null
            && SUPPORTED_MARKETS.contains(normalizeMarket(request.market()))
            && StringUtils.hasText(request.stockCode());
    }

    public BigDecimal currentPrice(Holding holding) {
        return quote(MarketDataRequest.from(holding)).currentPrice();
    }

    @Override
    public StockQuote quote(MarketDataRequest request) {
        ensureQuoteConfigured();

        KisPriceResponse response;
        try {
            response = restClient.get()
                .uri(priceUri(request.stockCode()))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .header("appkey", properties.getAppKey())
                .header("appsecret", properties.getAppSecret())
                .header("tr_id", properties.getTransactionId())
                .header("custtype", properties.getCustomerType())
                .retrieve()
                .body(KisPriceResponse.class);
        } catch (RestClientException exception) {
            throw KisApiErrors.requestFailure("QUOTE", "현재가", exception);
        }

        return parseQuote(request, response);
    }

    @Override
    public List<StockCandle> candles(MarketDataRequest request, CandleInterval interval, int count) {
        ensureCandleConfigured();
        String periodCode = periodCode(interval);

        KisCandleResponse response;
        try {
            response = restClient.get()
                .uri(candleUri(request.stockCode(), interval, periodCode, count))
                .accept(MediaType.APPLICATION_JSON)
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + accessToken())
                .header("appkey", properties.getAppKey())
                .header("appsecret", properties.getAppSecret())
                .header("tr_id", properties.getCandleTransactionId())
                .header("custtype", properties.getCustomerType())
                .retrieve()
                .body(KisCandleResponse.class);
        } catch (RestClientException exception) {
            throw KisApiErrors.requestFailure("CANDLES", "기간별 시세", exception);
        }

        if (response == null) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 기간별 시세 응답이 비어 있습니다.");
        }
        if (StringUtils.hasText(response.resultCode()) && !"0".equals(response.resultCode())) {
            throw KisApiErrors.responseFailure("CANDLES", "기간별 시세", response.resultCode(), response.messageCode());
        }
        if (response.output2() == null) {
            return List.of();
        }

        List<StockCandle> candles = response.output2().stream()
            .filter(item -> StringUtils.hasText(item.date()))
            .map(item -> toCandle(request, interval, item))
            .sorted(Comparator.comparing(StockCandle::dateTime))
            .toList();
        return candles.size() <= count ? candles : candles.subList(candles.size() - count, candles.size());
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
            throw KisApiErrors.requestFailure("TOKEN", "access token 발급", exception);
        }

        if (response == null || !StringUtils.hasText(response.accessToken())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 access token 응답이 올바르지 않습니다.");
        }

        return new AccessToken(response.accessToken(), tokenExpiresAt(response));
    }

    private StockQuote parseQuote(MarketDataRequest request, KisPriceResponse response) {
        if (response == null) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 응답이 비어 있습니다.");
        }
        if (StringUtils.hasText(response.resultCode()) && !"0".equals(response.resultCode())) {
            throw KisApiErrors.responseFailure("QUOTE", "현재가", response.resultCode(), response.messageCode());
        }
        if (response.output() == null || !StringUtils.hasText(response.output().currentPrice())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 현재가 응답에 현재가가 없습니다.");
        }

        Output output = response.output();
        return new StockQuote(
            PROVIDER_CODE,
            request.stockCode(),
            "",
            normalizeMarket(request.market()),
            requiredDecimal(output.currentPrice(), "한국투자증권 현재가 형식이 올바르지 않습니다."),
            decimal(output.changePrice()),
            decimal(output.changeRate()),
            decimal(output.volume()),
            decimal(output.openPrice()),
            decimal(output.highPrice()),
            decimal(output.lowPrice()),
            decimal(output.previousClose()),
            Instant.now()
        );
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

    private URI candleUri(String stockCode, CandleInterval interval, String periodCode, int count) {
        LocalDate endDate = LocalDate.now(ZoneId.of("Asia/Seoul"));
        LocalDate startDate = switch (interval) {
            case DAILY -> endDate.minusDays(count * 2L + 30L);
            case WEEKLY -> endDate.minusWeeks(count + 10L);
            case MONTHLY -> endDate.minusMonths(count + 3L);
            case MINUTE -> endDate;
        };
        DateTimeFormatter formatter = DateTimeFormatter.BASIC_ISO_DATE;
        return UriComponentsBuilder
            .fromUri(endpoint(properties.getCandlePath()))
            .queryParam("FID_COND_MRKT_DIV_CODE", DOMESTIC_STOCK_MARKET_DIVISION)
            .queryParam("FID_INPUT_ISCD", stockCode)
            .queryParam("FID_INPUT_DATE_1", startDate.format(formatter))
            .queryParam("FID_INPUT_DATE_2", endDate.format(formatter))
            .queryParam("FID_PERIOD_DIV_CODE", periodCode)
            .queryParam("FID_ORG_ADJ_PRC", "0")
            .build()
            .encode()
            .toUri();
    }

    private URI endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return URI.create(properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath);
    }

    private void ensureQuoteConfigured() {
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

    private void ensureCandleConfigured() {
        if (!StringUtils.hasText(properties.getBaseUrl())
            || !StringUtils.hasText(properties.getAppKey())
            || !StringUtils.hasText(properties.getAppSecret())
            || !StringUtils.hasText(properties.getCandleTransactionId())
            || !StringUtils.hasText(properties.getCustomerType())
            || !StringUtils.hasText(properties.getTokenPath())
            || !StringUtils.hasText(properties.getCandlePath())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 기간별 시세 API 설정이 필요합니다.");
        }
    }

    private String periodCode(CandleInterval interval) {
        if (interval == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 주기가 필요합니다.");
        }
        return switch (interval) {
            case DAILY -> "D";
            case WEEKLY -> "W";
            case MONTHLY -> "M";
            case MINUTE -> throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                "한국투자증권 기간별 시세 API는 분봉을 지원하지 않습니다."
            );
        };
    }

    private StockCandle toCandle(MarketDataRequest request, CandleInterval interval, CandleOutput item) {
        try {
            return new StockCandle(
                PROVIDER_CODE,
                request.stockCode(),
                normalizeMarket(request.market()),
                LocalDate.parse(item.date(), DateTimeFormatter.BASIC_ISO_DATE).atStartOfDay(),
                interval,
                requiredDecimal(item.openPrice(), "한국투자증권 시가 형식이 올바르지 않습니다."),
                requiredDecimal(item.highPrice(), "한국투자증권 고가 형식이 올바르지 않습니다."),
                requiredDecimal(item.lowPrice(), "한국투자증권 저가 형식이 올바르지 않습니다."),
                requiredDecimal(item.closePrice(), "한국투자증권 종가 형식이 올바르지 않습니다."),
                requiredDecimal(item.volume(), "한국투자증권 거래량 형식이 올바르지 않습니다.")
            );
        } catch (DateTimeParseException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "한국투자증권 기간별 시세 일자 형식이 올바르지 않습니다.");
        }
    }

    private String normalizeMarket(String market) {
        return market == null ? "" : market.trim().toUpperCase(Locale.ROOT);
    }

    private BigDecimal requiredDecimal(String value, String message) {
        if (!StringUtils.hasText(value)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
        try {
            return new BigDecimal(value.replace(",", "").replace("%", "").trim());
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, message);
        }
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

        @JsonProperty("msg_cd")
        String messageCode,

        Output output
    ) {
    }

    private record KisCandleResponse(
        @JsonProperty("rt_cd")
        String resultCode,

        @JsonProperty("msg1")
        String message,

        @JsonProperty("msg_cd")
        String messageCode,

        List<CandleOutput> output2
    ) {
    }

    private record CandleOutput(
        @JsonProperty("stck_bsop_date")
        String date,

        @JsonProperty("stck_oprc")
        String openPrice,

        @JsonProperty("stck_hgpr")
        String highPrice,

        @JsonProperty("stck_lwpr")
        String lowPrice,

        @JsonProperty("stck_clpr")
        String closePrice,

        @JsonProperty("acml_vol")
        String volume
    ) {
    }

    private record Output(
        @JsonProperty("stck_prpr")
        String currentPrice,

        @JsonProperty("prdy_vrss")
        String changePrice,

        @JsonProperty("prdy_ctrt")
        String changeRate,

        @JsonProperty("acml_vol")
        String volume,

        @JsonProperty("stck_oprc")
        String openPrice,

        @JsonProperty("stck_hgpr")
        String highPrice,

        @JsonProperty("stck_lwpr")
        String lowPrice,

        @JsonProperty("stck_sdpr")
        String previousClose
    ) {
    }
}
