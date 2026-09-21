package com.sagopalgo.api.market.client;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

/**
 * KB증권 IVU10140 현재가 API를 앱 내부 표준 시세 모델로 변환하는 Provider입니다.
 */
@Component
@Order(10)
public class KbMarketDataProvider implements MarketDataProvider {

    private static final String PROVIDER_CODE = "KB";
    private static final Set<String> SUPPORTED_MARKETS = Set.of("KOSPI", "KOSDAQ", "KONEX");

    private final KbSecuritiesAccountClient client;

    public KbMarketDataProvider(KbSecuritiesAccountClient client) {
        this.client = client;
    }

    @Override
    public String providerCode() {
        return PROVIDER_CODE;
    }

    @Override
    public boolean supports(MarketDataRequest request) {
        return client.isMarketDataEnabled()
            && request != null
            && SUPPORTED_MARKETS.contains(normalizeMarket(request.market()))
            && StringUtils.hasText(request.stockCode());
    }

    @Override
    public StockQuote quote(MarketDataRequest request) {
        JsonNode response = client.fetchCurrentPrice(request.stockCode());
        String currentPrice = client.text(response, "now_prc");
        if (!StringUtils.hasText(currentPrice)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 현재가 응답에 현재가가 없습니다.");
        }

        return new StockQuote(
            PROVIDER_CODE,
            request.stockCode(),
            client.text(response, "is_nm"),
            normalizeMarket(request.market()),
            decimal(currentPrice),
            client.decimal(response, "bdy_cmpr"),
            client.decimal(response, "up_dwn_r_p2"),
            client.decimal(response, "acml_vlm"),
            client.decimal(response, "opn_prc"),
            client.decimal(response, "hgh_prc"),
            client.decimal(response, "lw_prc"),
            client.decimal(response, "bdy_cls_prc"),
            Instant.now()
        );
    }

    @Override
    public List<StockCandle> candles(MarketDataRequest request, CandleInterval interval, int count) {
        JsonNode response = client.fetchCandles(request.stockCode(), request.market(), interval, count);
        List<StockCandle> candles = client.items(response, "out2")
            .stream()
            .map(item -> toCandle(request, interval, item))
            .sorted(Comparator.comparing(StockCandle::dateTime))
            .toList();
        return candles.size() <= count ? candles : candles.subList(candles.size() - count, candles.size());
    }

    private StockCandle toCandle(MarketDataRequest request, CandleInterval interval, JsonNode item) {
        String date = client.text(item, "dt");
        if (!StringUtils.hasText(date)) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 통합차트 응답에 일자가 없습니다.");
        }
        try {
            return new StockCandle(
                PROVIDER_CODE,
                request.stockCode(),
                normalizeMarket(request.market()),
                LocalDate.parse(date, DateTimeFormatter.BASIC_ISO_DATE).atStartOfDay(),
                interval,
                decimal(client.text(item, "opn_prc_p2")),
                decimal(client.text(item, "hgh_prc_p2")),
                decimal(client.text(item, "lw_prc_p2")),
                decimal(client.text(item, "cls_prc_p2")),
                decimal(client.text(item, "vlm"))
            );
        } catch (DateTimeParseException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 통합차트 일자 형식이 올바르지 않습니다.");
        }
    }

    private BigDecimal decimal(String value) {
        try {
            return new BigDecimal(value.replace(",", "").replace("%", "").trim());
        } catch (NumberFormatException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "KB증권 현재가 형식이 올바르지 않습니다.");
        }
    }

    private String normalizeMarket(String market) {
        return market == null ? "" : market.trim().toUpperCase(Locale.ROOT);
    }
}
