package com.sagopalgo.api.market.client;

import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;

/**
 * 외부 시세 공급자별 현재가 조회 경계입니다.
 */
public interface MarketPriceClient {

    boolean supports(Holding holding);

    BigDecimal currentPrice(Holding holding);
}
