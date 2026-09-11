package com.sagopalgo.api.market.service;

import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;
import java.util.Map;
import org.springframework.stereotype.Service;

/**
 * MVP 단계에서 외부 시세 API 대신 사용할 결정적 현재가 공급 서비스입니다.
 *
 * <p>이 서비스 경계만 실제 증권/시세 API 클라이언트로 교체하면 보유 종목 손익과 추천 점수 계산부는
 * 그대로 유지할 수 있습니다.
 */
@Service
public class MarketPriceService {

    private static final Map<String, BigDecimal> SAMPLE_PRICES = Map.of(
        key("005930", "KOSPI"), new BigDecimal("75300"),
        key("035420", "KOSPI"), new BigDecimal("184800"),
        key("005380", "KOSPI"), new BigDecimal("215900"),
        key("000660", "KOSPI"), new BigDecimal("142000"),
        key("035720", "KOSPI"), new BigDecimal("62200")
    );

    public BigDecimal currentPrice(Holding holding) {
        return SAMPLE_PRICES.getOrDefault(
            key(holding.getStockCode(), holding.getMarket()),
            holding.getBuyPrice()
        );
    }

    private static String key(String stockCode, String market) {
        return stockCode + ":" + market;
    }
}
