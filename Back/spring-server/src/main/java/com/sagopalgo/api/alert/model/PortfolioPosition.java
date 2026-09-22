package com.sagopalgo.api.alert.model;

import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.StockQuote;

/**
 * 포트폴리오 위험 평가에서 함께 사용하는 보유 정보와 조회 시세입니다.
 */
public record PortfolioPosition(Holding holding, StockQuote quote) {
}
