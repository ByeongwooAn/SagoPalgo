package com.sagopalgo.api.market.client;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.kb.client.KbSecuritiesAccountClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.Instant;
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
