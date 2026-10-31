package com.sagopalgo.api.market.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.dto.MarketStockInfoResponse;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.DomesticStockIdentity;
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

    public DomesticStockIdentity lookupDomesticStock(String stockCode) {
        String code = stockCode == null ? "" : stockCode.trim();
        if (!code.matches("[0-9]{6}")) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "국내 종목코드 6자리를 입력하세요.");
        }
        ApiException lastFailure = null;
        for (MarketDataProvider provider : providers) {
            try {
                var result = provider.domesticStockIdentity(code);
                if (result.isEmpty()) continue;
                DomesticStockIdentity identity = result.orElseThrow();
                if (!code.equals(identity.stockCode()) || !provider.providerCode().equals(identity.provider())
                    || !StringUtils.hasText(identity.stockName()) || identity.stockName().trim().length() > 100
                    || identity.market() == null || !List.of("KOSPI", "KOSDAQ", "KONEX").contains(identity.market())) {
                    throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "조회한 종목명·코드·시장을 확인할 수 없습니다.");
                }
                return new DomesticStockIdentity(identity.provider(), code, identity.stockName().trim(), identity.market());
            } catch (ApiException exception) {
                if (exception.getErrorCode() != ErrorCode.EXTERNAL_DATA_ERROR) throw exception;
                lastFailure = exception;
            }
        }
        if (lastFailure != null) throw lastFailure;
        throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,
            "종목 자동 조회를 사용할 수 없습니다. 서버의 KIS 또는 Toss 종목정보 연동 설정을 확인하거나 직접 입력하세요.");
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
