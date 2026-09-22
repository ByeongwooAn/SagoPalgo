package com.sagopalgo.api.market.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.dto.MarketStockInfoResponse;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.provider.MarketDataProvider;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 종목 기본 정보를 지원하는 Provider를 우선순위대로 선택합니다.
 */
@Service
public class MarketStockInfoService {

    private final List<MarketDataProvider> providers;

    public MarketStockInfoService(List<MarketDataProvider> providers) {
        this.providers = providers;
    }

    public MarketStockInfoResponse getStockInfo(String stockCode, String market) {
        MarketDataRequest request = validateRequest(stockCode, market);
        ApiException lastFailure = null;

        for (MarketDataProvider provider : providers) {
            if (!provider.supports(request)) {
                continue;
            }
            try {
                var result = provider.stockInfo(request);
                if (result.isPresent()) {
                    return MarketStockInfoResponse.from(result.orElseThrow());
                }
            } catch (ApiException exception) {
                if (exception.getErrorCode() != ErrorCode.EXTERNAL_DATA_ERROR) {
                    throw exception;
                }
                lastFailure = exception;
            }
        }

        if (lastFailure != null) {
            throw lastFailure;
        }
        throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "사용 가능한 종목 정보 Provider가 없습니다.");
    }

    private MarketDataRequest validateRequest(String stockCode, String market) {
        if (!StringUtils.hasText(stockCode)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "종목코드가 필요합니다.");
        }
        if (!StringUtils.hasText(market)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "시장이 필요합니다.");
        }
        return new MarketDataRequest(
            stockCode.trim(),
            market.trim().toUpperCase(Locale.ROOT)
        );
    }
}
