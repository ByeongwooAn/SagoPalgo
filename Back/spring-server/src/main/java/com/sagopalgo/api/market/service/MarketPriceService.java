package com.sagopalgo.api.market.service;

import com.sagopalgo.api.holding.model.Holding;
import java.math.BigDecimal;
import org.springframework.stereotype.Service;

/**
 * 보유 종목의 현재가를 공급하는 서비스 경계입니다.
 *
 * <p>아직 실제 증권/시세 API가 연결되지 않았으므로 임의 샘플 가격을 만들지 않고 사용자가 등록한
 * 매수가를 현재가로 반환합니다. 실제 시세 API가 붙으면 이 서비스만 교체합니다.
 */
@Service
public class MarketPriceService {

    public BigDecimal currentPrice(Holding holding) {
        return holding.getBuyPrice();
    }
}
