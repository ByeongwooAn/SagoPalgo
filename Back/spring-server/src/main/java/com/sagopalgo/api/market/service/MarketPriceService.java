package com.sagopalgo.api.market.service;

import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.client.MarketPriceClient;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.stereotype.Service;

/**
 * 보유 종목의 현재가를 공급하는 서비스 경계입니다.
 */
@Service
public class MarketPriceService {

    private final List<MarketPriceClient> clients;

    public MarketPriceService(List<MarketPriceClient> clients) {
        this.clients = clients;
    }

    public BigDecimal currentPrice(Holding holding) {
        return clients.stream()
            .filter(client -> client.supports(holding))
            .findFirst()
            .map(client -> client.currentPrice(holding))
            .orElseGet(holding::getBuyPrice);
    }
}
