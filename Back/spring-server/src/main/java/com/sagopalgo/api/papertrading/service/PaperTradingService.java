package com.sagopalgo.api.papertrading.service;

import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.dto.PaperBuyRequest;
import com.sagopalgo.api.papertrading.dto.PaperPositionResponse;
import com.sagopalgo.api.papertrading.dto.PaperSellRequest;
import com.sagopalgo.api.papertrading.dto.PaperTradeResponse;
import com.sagopalgo.api.papertrading.dto.PaperTradingSnapshotResponse;
import com.sagopalgo.api.papertrading.dto.PaperTradingSummaryResponse;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * AI 추천을 실제 주문 없이 가상 체결하고 포트폴리오 성과를 계산합니다.
 */
@Service
public class PaperTradingService {

    private static final int MONEY_SCALE = 2;
    private static final int QUANTITY_SCALE = 4;
    private static final int RATE_SCALE = 2;

    private final PaperTradeMapper tradeMapper;
    private final CapitalService capitalService;
    private final RecommendationService recommendationService;
    private final MarketPriceService marketPriceService;

    public PaperTradingService(
        PaperTradeMapper tradeMapper,
        CapitalService capitalService,
        RecommendationService recommendationService,
        MarketPriceService marketPriceService
    ) {
        this.tradeMapper = tradeMapper;
        this.capitalService = capitalService;
        this.recommendationService = recommendationService;
        this.marketPriceService = marketPriceService;
    }

    @Transactional(readOnly = true)
    public PaperTradingSnapshotResponse getSnapshot(Long userId) {
        BigDecimal initialCapital = initialCapital(userId);
        List<PaperTradeRecord> records = tradeMapper.findAllByUserId(userId);
        return snapshot(initialCapital, records);
    }

    @Transactional
    public PaperTradingSnapshotResponse buyFromRecommendation(
        Long userId,
        Long recommendationId,
        PaperBuyRequest request
    ) {
        tradeMapper.lockUser(userId);
        RecommendationResponse recommendation = recommendationService.findOne(userId, recommendationId);
        if (!"BUY".equalsIgnoreCase(recommendation.recommendationType())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "매수 AI 신호만 모의매수할 수 있습니다.");
        }

        BigDecimal quantity = normalizeQuantity(request.quantity());
        StockQuote quote = executionQuote(recommendation.stockCode(), recommendation.market());
        BigDecimal price = normalizeMoney(quote.currentPrice());
        BigDecimal amount = price.multiply(quantity);
        BigDecimal initialCapital = initialCapital(userId);
        Ledger ledger = ledger(initialCapital, tradeMapper.findAllByUserId(userId));
        if (amount.compareTo(ledger.cashBalance) > 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "모의매매 현금 잔액이 부족합니다.");
        }

        PaperTradeRecord record = baseRecord(
            userId,
            recommendation.stockCode(),
            recommendation.stockName(),
            recommendation.market(),
            "BUY",
            price,
            quantity
        );
        record.setRecommendationId(recommendationId);
        record.setRealizedProfit(BigDecimal.ZERO);
        record.setMemo("AI " + recommendation.statusLabel() + " 신호 모의매수");
        tradeMapper.insert(record);
        return snapshot(initialCapital, tradeMapper.findAllByUserId(userId));
    }

    @Transactional
    public PaperTradingSnapshotResponse sell(Long userId, PaperSellRequest request) {
        tradeMapper.lockUser(userId);
        String stockCode = request.stockCode().trim();
        String market = request.market().trim().toUpperCase(Locale.ROOT);
        BigDecimal quantity = normalizeQuantity(request.quantity());
        BigDecimal initialCapital = initialCapital(userId);
        List<PaperTradeRecord> records = tradeMapper.findAllByUserId(userId);
        Ledger ledger = ledger(initialCapital, records);
        PositionState position = ledger.positions.get(positionKey(stockCode, market));
        if (position == null || position.quantity.signum() <= 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "매도할 모의 포지션이 없습니다.");
        }
        if (quantity.compareTo(position.quantity) > 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "보유한 모의 수량보다 많이 매도할 수 없습니다.");
        }

        StockQuote quote = executionQuote(stockCode, market);
        BigDecimal price = normalizeMoney(quote.currentPrice());
        BigDecimal realizedProfit = price.subtract(position.averagePrice())
            .multiply(quantity)
            .setScale(MONEY_SCALE, RoundingMode.HALF_UP);
        PaperTradeRecord record = baseRecord(
            userId,
            stockCode,
            position.stockName,
            market,
            "SELL",
            price,
            quantity
        );
        record.setRealizedProfit(realizedProfit);
        record.setMemo("모의 포지션 현재가 매도");
        tradeMapper.insert(record);
        return snapshot(initialCapital, tradeMapper.findAllByUserId(userId));
    }

    private PaperTradingSnapshotResponse snapshot(
        BigDecimal initialCapital,
        List<PaperTradeRecord> records
    ) {
        Ledger ledger = ledger(initialCapital, records);
        List<PaperPositionResponse> positions = new ArrayList<>();
        BigDecimal openPositionValue = BigDecimal.ZERO;
        BigDecimal unrealizedProfit = BigDecimal.ZERO;

        for (PositionState position : ledger.positions.values()) {
            if (position.quantity.signum() <= 0) {
                continue;
            }
            StockQuote quote = marketPriceService.quoteMarket(
                new MarketDataRequest(position.stockCode, position.market)
            );
            BigDecimal currentPrice = quote.currentPrice() != null && quote.currentPrice().signum() > 0
                ? quote.currentPrice()
                : position.averagePrice();
            BigDecimal valuation = currentPrice.multiply(position.quantity);
            BigDecimal profit = valuation.subtract(position.totalCost);
            BigDecimal profitRate = position.totalCost.signum() > 0
                ? profit.divide(position.totalCost, 6, RoundingMode.HALF_UP)
                    .multiply(new BigDecimal("100"))
                : BigDecimal.ZERO;
            openPositionValue = openPositionValue.add(valuation);
            unrealizedProfit = unrealizedProfit.add(profit);
            positions.add(new PaperPositionResponse(
                position.stockCode,
                position.stockName,
                position.market,
                quote.currentPrice() != null && quote.currentPrice().signum() > 0
                    ? quote.provider()
                    : "FALLBACK",
                quantity(position.quantity),
                money(position.averagePrice()),
                money(currentPrice),
                money(valuation),
                money(profit),
                rate(profitRate)
            ));
        }

        BigDecimal totalAsset = ledger.cashBalance.add(openPositionValue);
        BigDecimal totalProfit = totalAsset.subtract(initialCapital);
        BigDecimal returnRate = initialCapital.signum() > 0
            ? totalProfit.divide(initialCapital, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"))
            : BigDecimal.ZERO;
        BigDecimal winRate = ledger.completedTrades > 0
            ? BigDecimal.valueOf(ledger.winningTrades)
                .divide(BigDecimal.valueOf(ledger.completedTrades), 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"))
            : BigDecimal.ZERO;
        BigDecimal turnoverRate = initialCapital.signum() > 0
            ? ledger.turnover.divide(initialCapital, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"))
            : BigDecimal.ZERO;

        List<PaperTradeResponse> trades = records.stream()
            .map(this::tradeResponse)
            .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
        Collections.reverse(trades);
        return new PaperTradingSnapshotResponse(
            new PaperTradingSummaryResponse(
                money(initialCapital),
                money(ledger.cashBalance),
                money(openPositionValue),
                money(totalAsset),
                money(ledger.realizedProfit),
                money(unrealizedProfit),
                money(totalProfit),
                rate(returnRate),
                ledger.completedTrades,
                rate(winRate),
                money(ledger.maxLoss),
                rate(turnoverRate)
            ),
            positions,
            trades
        );
    }

    private Ledger ledger(BigDecimal initialCapital, List<PaperTradeRecord> records) {
        Ledger ledger = new Ledger(initialCapital);
        for (PaperTradeRecord record : records) {
            BigDecimal amount = record.getTradePrice().multiply(record.getQuantity());
            ledger.turnover = ledger.turnover.add(amount);
            PositionState position = ledger.positions.computeIfAbsent(
                positionKey(record.getStockCode(), record.getMarket()),
                ignored -> new PositionState(
                    record.getStockCode(),
                    record.getStockName(),
                    record.getMarket()
                )
            );
            if ("BUY".equalsIgnoreCase(record.getTradeType())) {
                ledger.cashBalance = ledger.cashBalance.subtract(amount);
                position.buy(record.getTradePrice(), record.getQuantity());
                continue;
            }

            ledger.cashBalance = ledger.cashBalance.add(amount);
            position.sell(record.getQuantity());
            BigDecimal realized = record.getRealizedProfit() == null
                ? BigDecimal.ZERO
                : record.getRealizedProfit();
            ledger.realizedProfit = ledger.realizedProfit.add(realized);
            ledger.completedTrades++;
            if (realized.signum() > 0) {
                ledger.winningTrades++;
            } else if (realized.signum() < 0 && realized.abs().compareTo(ledger.maxLoss) > 0) {
                ledger.maxLoss = realized.abs();
            }
        }
        return ledger;
    }

    private StockQuote executionQuote(String stockCode, String market) {
        StockQuote quote = marketPriceService.quoteMarket(new MarketDataRequest(stockCode, market));
        if (quote.currentPrice() == null || quote.currentPrice().signum() <= 0
            || "FALLBACK".equalsIgnoreCase(quote.provider())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "실제 현재가를 확인할 수 없어 모의 체결하지 않았습니다.");
        }
        return quote;
    }

    private PaperTradeRecord baseRecord(
        Long userId,
        String stockCode,
        String stockName,
        String market,
        String tradeType,
        BigDecimal price,
        BigDecimal quantity
    ) {
        PaperTradeRecord record = new PaperTradeRecord();
        record.setUserId(userId);
        record.setStockCode(stockCode);
        record.setStockName(stockName);
        record.setMarket(market);
        record.setTradeType(tradeType);
        record.setExecutionMode("PAPER");
        record.setTradePrice(price);
        record.setQuantity(quantity);
        record.setTradeDate(LocalDateTime.now());
        return record;
    }

    private PaperTradeResponse tradeResponse(PaperTradeRecord record) {
        return new PaperTradeResponse(
            record.getTradeRecordId(),
            record.getRecommendationId(),
            record.getStockCode(),
            record.getStockName(),
            record.getMarket(),
            record.getTradeType(),
            money(record.getTradePrice()),
            quantity(record.getQuantity()),
            money(record.getTradePrice().multiply(record.getQuantity())),
            money(record.getRealizedProfit() == null ? BigDecimal.ZERO : record.getRealizedProfit()),
            record.getTradeDate(),
            record.getMemo()
        );
    }

    private BigDecimal initialCapital(Long userId) {
        BigDecimal capital = capitalService.findByUserId(userId).availableCapital();
        if (capital == null || capital.signum() <= 0) {
            throw new ApiException(ErrorCode.PAPER_CAPITAL_REQUIRED);
        }
        return capital;
    }

    private String positionKey(String stockCode, String market) {
        return stockCode.trim() + ":" + market.trim().toUpperCase(Locale.ROOT);
    }

    private BigDecimal normalizeMoney(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }

    private BigDecimal normalizeQuantity(BigDecimal value) {
        return value.setScale(QUANTITY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal money(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal quantity(BigDecimal value) {
        return value.setScale(QUANTITY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal rate(BigDecimal value) {
        return value.setScale(RATE_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private static final class Ledger {
        private final Map<String, PositionState> positions = new LinkedHashMap<>();
        private BigDecimal cashBalance;
        private BigDecimal realizedProfit = BigDecimal.ZERO;
        private BigDecimal turnover = BigDecimal.ZERO;
        private BigDecimal maxLoss = BigDecimal.ZERO;
        private long completedTrades;
        private long winningTrades;

        private Ledger(BigDecimal initialCapital) {
            this.cashBalance = initialCapital;
        }
    }

    private static final class PositionState {
        private final String stockCode;
        private final String stockName;
        private final String market;
        private BigDecimal quantity = BigDecimal.ZERO;
        private BigDecimal totalCost = BigDecimal.ZERO;

        private PositionState(String stockCode, String stockName, String market) {
            this.stockCode = stockCode;
            this.stockName = stockName;
            this.market = market;
        }

        private void buy(BigDecimal price, BigDecimal boughtQuantity) {
            quantity = quantity.add(boughtQuantity);
            totalCost = totalCost.add(price.multiply(boughtQuantity));
        }

        private void sell(BigDecimal soldQuantity) {
            totalCost = totalCost.subtract(averagePrice().multiply(soldQuantity));
            quantity = quantity.subtract(soldQuantity);
            if (quantity.signum() == 0) {
                totalCost = BigDecimal.ZERO;
            }
        }

        private BigDecimal averagePrice() {
            return quantity.signum() > 0
                ? totalCost.divide(quantity, 8, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;
        }
    }
}
