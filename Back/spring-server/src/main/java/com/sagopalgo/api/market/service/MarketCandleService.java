package com.sagopalgo.api.market.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.util.List;
import java.util.Locale;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 캔들 조회를 지원하는 시세 Provider를 우선순위대로 선택합니다.
 */
@Service
public class MarketCandleService {

    private static final int MAX_CANDLE_COUNT = 100;
    private static final Logger log = LoggerFactory.getLogger(MarketCandleService.class);

    private final List<MarketDataProvider> providers;

    public MarketCandleService(List<MarketDataProvider> providers) {
        this.providers = providers;
    }

    public MarketCandleResponse getCandles(
        String stockCode,
        String market,
        CandleInterval interval,
        int count
    ) {
        MarketDataRequest request = validateRequest(stockCode, market, interval, count);
        ApiException lastFailure = null;

        for (MarketDataProvider provider : providers) {
            if (!provider.supports(request)) {
                continue;
            }
            try {
                List<StockCandle> candles = provider.candles(request, interval, count);
                if (candles == null || candles.isEmpty()) {
                    log.warn(
                        "캔들 Provider가 빈 결과를 반환했습니다. provider={} stockCode={}",
                        provider.providerCode(),
                        request.stockCode()
                    );
                    continue;
                }
                return new MarketCandleResponse(
                    provider.providerCode(),
                    request.stockCode(),
                    request.market(),
                    interval,
                    candles.size(),
                    List.copyOf(candles)
                );
            } catch (ApiException exception) {
                if (exception.getErrorCode() != ErrorCode.EXTERNAL_DATA_ERROR) {
                    throw exception;
                }
                lastFailure = exception;
                log.warn(
                    "캔들 Provider 조회 실패. provider={} stockCode={} message={}",
                    provider.providerCode(),
                    request.stockCode(),
                    exception.getMessage()
                );
            }
        }

        if (lastFailure != null) {
            throw lastFailure;
        }
        throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "사용 가능한 캔들 시세 Provider가 없습니다.");
    }

    private MarketDataRequest validateRequest(String stockCode, String market, CandleInterval interval, int count) {
        if (!StringUtils.hasText(stockCode)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "종목코드가 필요합니다.");
        }
        if (!StringUtils.hasText(market)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "시장이 필요합니다.");
        }
        if (interval == null || interval == CandleInterval.MINUTE) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 주기는 DAILY, WEEKLY, MONTHLY 중 하나여야 합니다.");
        }
        if (count < 1 || count > MAX_CANDLE_COUNT) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 조회 건수는 1~100이어야 합니다.");
        }
        return new MarketDataRequest(stockCode.trim(), market.trim().toUpperCase(Locale.ROOT));
    }
}
