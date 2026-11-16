package com.sagopalgo.api.market.service;

import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.model.UsStockExchange;
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
        if (UsStockExchange.fromMarket(request.market()).isPresent()) {
            return fallbackQuote(request, fallbackPrice == null ? BigDecimal.ZERO : fallbackPrice);
        }
        return quote(request, fallbackPrice);
    }

    public StockQuote quoteMarket(MarketDataRequest request) {
        if (UsStockExchange.fromMarket(request.market()).isPresent()) {
            return fallbackQuote(request, BigDecimal.ZERO);
        }
        return quote(request, BigDecimal.ZERO);
    }

    public StockQuote getUsQuote(String stockCode, String market) {
        if (UsStockExchange.fromMarket(market).isEmpty() || stockCode == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "미국 거래소와 종목 티커를 입력하세요.");
        }
        return quote(MarketDataRequest.forLookup(stockCode, market), null);
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
        if (UsStockExchange.fromMarket(request.market()).isPresent()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "사용 가능한 미국주식 현재가 Provider가 없습니다.");
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
