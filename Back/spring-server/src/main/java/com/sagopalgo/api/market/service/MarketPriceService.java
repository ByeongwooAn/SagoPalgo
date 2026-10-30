package com.sagopalgo.api.market.service;

import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.math.BigDecimal;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 보유 종목의 현재가를 공급하는 서비스 경계입니다.
 */
@Service
public class MarketPriceService {

    private static final Logger log = LoggerFactory.getLogger(MarketPriceService.class);

    private final List<MarketDataProvider> providers;

    public MarketPriceService(List<MarketDataProvider> providers) {
        this.providers = providers;
    }

    public BigDecimal currentPrice(Holding holding) {
        return quote(holding).currentPrice();
    }

    public StockQuote quote(Holding holding) {
        MarketDataRequest request = MarketDataRequest.from(holding);
        BigDecimal fallbackPrice = holding == null ? null : holding.getBuyPrice();
        return quote(request, fallbackPrice);
    }

    public StockQuote quoteMarket(MarketDataRequest request) {
        return quote(request, BigDecimal.ZERO);
    }

    private StockQuote quote(MarketDataRequest request, BigDecimal fallbackPrice) {
        ApiException lastFailure = null;

        for (MarketDataProvider provider : providers) {
            if (!provider.supports(request)) {
                continue;
            }
            try {
                StockQuote quote = provider.quote(request);
                if (quote == null || quote.currentPrice() == null || quote.currentPrice().signum() <= 0
                    || !provider.providerCode().equals(quote.provider())
                    || !request.stockCode().equals(quote.stockCode())) {
                    throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "현재가 응답의 가격·종목·출처가 올바르지 않습니다.");
                }
                return quote;
            } catch (ApiException exception) {
                if (exception.getErrorCode() != ErrorCode.EXTERNAL_DATA_ERROR) {
                    throw exception;
                }
                lastFailure = exception;
                log.warn(
                    "시세 Provider 조회 실패. provider={} stockCode={} message={}",
                    provider.providerCode(),
                    request.stockCode(),
                    exception.getMessage()
                );
            }
        }

        if (fallbackPrice != null) {
            return fallbackQuote(request, fallbackPrice);
        }
        if (lastFailure != null) {
            throw lastFailure;
        }
        return fallbackQuote(request, BigDecimal.ZERO);
    }

    private StockQuote fallbackQuote(MarketDataRequest request, BigDecimal price) {
        return new StockQuote(
            "FALLBACK",
            request.stockCode(),
            "",
            request.market(),
            price,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            java.time.Instant.now()
        );
    }
}
