package com.sagopalgo.api.papertrading.service;

import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.model.UsStockExchange;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.papertrading.dto.PaperBuyRequest;
import com.sagopalgo.api.papertrading.dto.PaperPositionResponse;
import com.sagopalgo.api.papertrading.dto.PaperSellRequest;
import com.sagopalgo.api.papertrading.dto.PaperTradeResponse;
import com.sagopalgo.api.papertrading.dto.PaperTradingSnapshotResponse;
import com.sagopalgo.api.papertrading.dto.PaperTradingSummaryResponse;
import com.sagopalgo.api.papertrading.dto.UsPaperTradeRequest;
import com.sagopalgo.api.papertrading.mapper.PaperTradeMapper;
import com.sagopalgo.api.papertrading.model.PaperTradeRecord;
import com.sagopalgo.api.recommendation.dto.DailySignal;
import com.sagopalgo.api.recommendation.service.DailySignalService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import org.springframework.beans.factory.annotation.Autowired;
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
    private static final int USD_PRICE_SCALE = 4;
    private static final long QUOTE_MAX_AGE_SECONDS = 15;

    private final PaperTradeMapper tradeMapper;
    private final CapitalService capitalService;
    private final RecommendationService recommendationService;
    private final MarketPriceService marketPriceService;
    private final KisMarketPriceClient kis;
    private final DailySignalService dailySignals;
    private final Clock clock;

    @Autowired
    public PaperTradingService(
        PaperTradeMapper tradeMapper,
        CapitalService capitalService,
        RecommendationService recommendationService,
        MarketPriceService marketPriceService,
        KisMarketPriceClient kis,
        DailySignalService dailySignals
    ) {
        this(tradeMapper, capitalService, recommendationService, marketPriceService, kis, dailySignals,
            Clock.systemDefaultZone());
    }

    PaperTradingService(
        PaperTradeMapper tradeMapper, CapitalService capitalService, RecommendationService recommendationService,
        MarketPriceService marketPriceService, KisMarketPriceClient kis, DailySignalService dailySignals, Clock clock
    ) {
        this.tradeMapper = tradeMapper;
        this.capitalService = capitalService;
        this.recommendationService = recommendationService;
        this.marketPriceService = marketPriceService;
        this.kis = kis;
        this.dailySignals = dailySignals;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public PaperTradingSnapshotResponse getSnapshot(Long userId) {
        BigDecimal initialCapital = initialCapital(userId);
        List<PaperTradeRecord> records = tradeMapper.findAllByUserId(userId);
        return snapshot(initialCapital, records);
    }

    @Transactional(readOnly = true)
    public PaperTradingSnapshotResponse getUsSnapshot(Long userId) {
        BigDecimal capital = tradeMapper.findUsCapital(userId);
        return capital == null
            ? snapshot(BigDecimal.ZERO, List.of(), true, null)
            : snapshot(capital, tradeMapper.findUsTrades(userId), true, null);
    }

    @Transactional
    public PaperTradingSnapshotResponse openUsAccount(Long userId, BigDecimal capital) {
        tradeMapper.lockUser(userId);
        BigDecimal existing = tradeMapper.findUsCapital(userId);
        if (existing == null) {
            tradeMapper.insertUsAccount(userId, capital);
            return snapshot(capital, List.of(), true, null);
        }
        if (existing.compareTo(capital) != 0) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "이미 USD 모의계좌가 개설되어 있습니다.");
        }
        return snapshot(existing, tradeMapper.findUsTrades(userId), true, null);
    }

    @Transactional
    public PaperTradingSnapshotResponse tradeUs(Long userId, UsPaperTradeRequest order) {
        if (UsStockExchange.fromMarket(order.market()).isEmpty()) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "미국주식 거래소를 선택하세요.");
        }
        MarketDataRequest symbol = MarketDataRequest.forLookup(order.stockCode(), order.market());
        BigDecimal quantity = normalizeQuantity(order.quantity());
        tradeMapper.lockUser(userId);
        BigDecimal capital = tradeMapper.findUsCapital(userId);
        if (capital == null) {
            throw new ApiException(ErrorCode.PAPER_CAPITAL_REQUIRED, "USD 모의계좌와 시작 자금을 먼저 설정하세요.");
        }
        List<PaperTradeRecord> records = tradeMapper.findUsTrades(userId);
        if (isReplay(records, order.requestId(), symbol, order.side().name(), quantity, null)) {
            return snapshot(capital, records, true, null);
        }

        Ledger ledger = ledger(capital, records, true);
        PositionState position = ledger.positions.get(positionKey(symbol.stockCode(), symbol.market()));
        boolean buy = order.side() == UsPaperTradeRequest.Side.BUY;
        if (!buy && (position == null || quantity.compareTo(position.quantity) > 0)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "보유한 미국주식 모의 수량보다 많이 매도할 수 없습니다.");
        }

        DailySignal signal = null;
        if (buy && DailySignalService.supportsUs(symbol.stockCode(), symbol.market())) {
            signal = dailySignals.analyze(symbol.stockCode(), symbol.market());
            requireBuySignal(signal, clock.instant());
        }
        StockQuote quote = executionQuote(symbol, true);
        BigDecimal price = quote.currentPrice().setScale(USD_PRICE_SCALE, RoundingMode.HALF_UP);
        BigDecimal amount = tradeAmount(price, quantity, true);
        if (amount.signum() <= 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "USD 모의 체결 금액은 최소 0.01 USD입니다.");
        }
        if (buy && amount.compareTo(ledger.cashBalance) > 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "USD 모의 현금 잔액이 부족합니다.");
        }
        String stockName = position != null ? position.stockName : symbol.stockCode();
        PaperTradeRecord record = baseRecord(
            userId, symbol.stockCode(), stockName, symbol.market(), order.side().name(), price, quantity
        );
        record.setRequestId(order.requestId());
        recordExecutionEvidence(record, quote, signal);
        record.setRealizedProfit(buy ? BigDecimal.ZERO : amount.subtract(position.usCostForSale(quantity)));
        record.setMemo(quote.provider() + " 현재가 미국주식 모의" + (buy ? "매수" : "매도"));
        tradeMapper.insertUsTrade(record);
        List<PaperTradeRecord> updated = new ArrayList<>(records);
        updated.add(record);
        return snapshot(capital, updated, true, quote);
    }

    @Transactional
    public PaperTradingSnapshotResponse buyFromRecommendation(
        Long userId,
        Long recommendationId,
        PaperBuyRequest request
    ) {
        tradeMapper.lockUser(userId);
        BigDecimal quantity = normalizeQuantity(request.quantity());
        BigDecimal initialCapital = initialCapital(userId);
        List<PaperTradeRecord> records = tradeMapper.findAllByUserId(userId);
        if (isReplay(records, request.requestId(), null, "BUY", quantity, recommendationId)) {
            return snapshot(initialCapital, records);
        }
        var recommendation = recommendationService.findOne(userId, recommendationId);
        var symbol = MarketDataRequest.forLookup(recommendation.stockCode(), recommendation.market());
        DailySignal signal = null;
        if (DailySignalService.supportsDomestic(symbol.stockCode(), symbol.market())) {
            signal = recommendation.evidence() == null ? null : recommendation.evidence().dailySignal();
            requireBuySignal(signal, clock.instant());
        } else if (!"BUY".equalsIgnoreCase(recommendation.recommendationType())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "매수 AI 신호만 모의매수할 수 있습니다.");
        }

        StockQuote quote = executionQuote(symbol, false);
        BigDecimal price = normalizeMoney(quote.currentPrice());
        BigDecimal amount = price.multiply(quantity);
        Ledger ledger = ledger(initialCapital, records, false);
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
        record.setRequestId(request.requestId());
        recordExecutionEvidence(record, quote, signal);
        record.setRealizedProfit(BigDecimal.ZERO);
        record.setMemo(signal == null ? "AI " + recommendation.statusLabel() + " 신호 모의매수" : "장 마감 모델 매수 관찰");
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
        var symbol = new MarketDataRequest(stockCode, market);
        if (isReplay(records, request.requestId(), symbol, "SELL", quantity, null)) {
            return snapshot(initialCapital, records);
        }
        Ledger ledger = ledger(initialCapital, records, false);
        PositionState position = ledger.positions.get(positionKey(stockCode, market));
        if (position == null || position.quantity.signum() <= 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "매도할 모의 포지션이 없습니다.");
        }
        if (quantity.compareTo(position.quantity) > 0) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "보유한 모의 수량보다 많이 매도할 수 없습니다.");
        }

        StockQuote quote = executionQuote(symbol, false);
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
        record.setRequestId(request.requestId());
        recordExecutionEvidence(record, quote, null);
        record.setMemo("모의 포지션 현재가 매도");
        tradeMapper.insert(record);
        return snapshot(initialCapital, tradeMapper.findAllByUserId(userId));
    }

    private PaperTradingSnapshotResponse snapshot(
        BigDecimal initialCapital,
        List<PaperTradeRecord> records
    ) {
        return snapshot(initialCapital, records, false, null);
    }

    private PaperTradingSnapshotResponse snapshot(
        BigDecimal initialCapital, List<PaperTradeRecord> records, boolean usd, StockQuote executedQuote
    ) {
        Ledger ledger = ledger(initialCapital, records, usd);
        List<PaperPositionResponse> positions = new ArrayList<>();
        BigDecimal openPositionValue = BigDecimal.ZERO;
        BigDecimal unrealizedProfit = BigDecimal.ZERO;

        for (PositionState position : ledger.positions.values()) {
            if (position.quantity.signum() <= 0) {
                continue;
            }
            StockQuote quote = valuationQuote(position, usd, executedQuote);
            boolean priced = quote != null && quote.currentPrice() != null && quote.currentPrice().signum() > 0;
            BigDecimal currentPrice = priced
                ? (usd ? price(quote.currentPrice(), true) : quote.currentPrice())
                : position.averagePrice();
            BigDecimal valuation = usd && !priced ? position.totalCost : tradeAmount(currentPrice, position.quantity, usd);
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
                priced ? quote.provider() : "FALLBACK",
                quantity(position.quantity),
                price(position.averagePrice(), usd),
                price(currentPrice, usd),
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
            .map(record -> tradeResponse(record, usd))
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
            trades,
            usd ? "USD" : "KRW"
        );
    }

    private StockQuote valuationQuote(PositionState position, boolean usd, StockQuote executedQuote) {
        if (!usd) {
            return marketPriceService.quoteMarket(new MarketDataRequest(position.stockCode, position.market));
        }
        if (executedQuote != null && position.stockCode.equals(executedQuote.stockCode())
            && position.market.equals(executedQuote.market())) return executedQuote;
        try {
            return marketPriceService.getUsQuote(position.stockCode, position.market);
        } catch (ApiException exception) {
            if (exception.getErrorCode() != ErrorCode.EXTERNAL_DATA_ERROR) throw exception;
            return null;
        }
    }

    private Ledger ledger(BigDecimal initialCapital, List<PaperTradeRecord> records, boolean usd) {
        Ledger ledger = new Ledger(initialCapital);
        for (PaperTradeRecord record : records) {
            BigDecimal amount = tradeAmount(record.getTradePrice(), record.getQuantity(), usd);
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
                position.buy(amount, record.getQuantity());
                continue;
            }

            ledger.cashBalance = ledger.cashBalance.add(amount);
            position.sell(record.getQuantity(), usd);
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

    private boolean isReplay(List<PaperTradeRecord> records, String requestId, MarketDataRequest symbol,
        String side, BigDecimal quantity, Long recommendationId) {
        for (PaperTradeRecord record : records) {
            if (!requestId.equals(record.getRequestId())) continue;
            if (!side.equals(record.getTradeType()) || quantity.compareTo(record.getQuantity()) != 0
                || !Objects.equals(recommendationId, record.getRecommendationId())
                || (symbol != null && (!symbol.stockCode().equals(record.getStockCode())
                    || !symbol.market().equals(record.getMarket())))) {
                throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "같은 요청 ID에 다른 모의주문을 사용할 수 없습니다.");
            }
            return true;
        }
        return false;
    }

    private void requireBuySignal(DailySignal signal, Instant at) {
        if (signal == null || !"BUY_WATCH".equals(signal.decision()) || signal.basisDate() == null
            || signal.modelSha256() == null || !signal.modelSha256().matches("[a-f0-9]{64}")
            || signal.evaluatedAt() == null || signal.evaluatedAt().toInstant().isAfter(at)
            || signal.expiresAt() == null) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "장 마감 모델의 매수 관찰 신호가 필요합니다.");
        }
        if (!at.isBefore(signal.expiresAt().toInstant())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "장 마감 모델의 매수 신호가 만료되었습니다.");
        }
    }

    private StockQuote executionQuote(MarketDataRequest symbol, boolean usd) {
        if (DailySignalService.supportsDomestic(symbol.stockCode(), symbol.market())
            || DailySignalService.supportsUs(symbol.stockCode(), symbol.market())) {
            Instant started = clock.instant();
            requireRegularSession(symbol, started);
            StockQuote quote = kis.todayTradeQuote(symbol, started);
            Instant now = clock.instant();
            requireRegularSession(symbol, now);
            if (quote == null || quote.marketAt() == null || quote.receivedAt() == null
                || quote.marketAt().isAfter(quote.receivedAt()) || quote.receivedAt().isAfter(now)
                || quote.marketAt().isBefore(now.minusSeconds(QUOTE_MAX_AGE_SECONDS))
                || !DailySignalService.isRegularSession(symbol, quote.marketAt())) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "15초 이내의 정규장 체결 시각을 확인할 수 없습니다.");
            }
            return requireExecutionPrice(quote);
        }
        return requireExecutionPrice(usd ? marketPriceService.getUsQuote(symbol.stockCode(), symbol.market())
            : marketPriceService.quoteMarket(symbol));
    }

    private void requireRegularSession(MarketDataRequest symbol, Instant now) {
        if (!DailySignalService.isRegularSession(symbol, now)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "정규장에만 이 종목의 모의 주문을 체결할 수 있습니다.");
        }
    }

    private StockQuote requireExecutionPrice(StockQuote quote) {
        if (quote == null || quote.currentPrice() == null || quote.currentPrice().signum() <= 0
            || "FALLBACK".equalsIgnoreCase(quote.provider())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "실제 현재가를 확인할 수 없어 모의 체결하지 않았습니다.");
        }
        return quote;
    }

    private void recordExecutionEvidence(PaperTradeRecord record, StockQuote quote, DailySignal signal) {
        Instant executedAt = clock.instant();
        if (signal != null) {
            requireBuySignal(signal, executedAt);
            record.setSignalBasisDate(signal.basisDate());
            record.setSignalModelSha256(signal.modelSha256());
            record.setSignalExpiresAt(utc(signal.expiresAt().toInstant()));
        }
        if (quote.marketAt() != null) {
            requireRegularSession(new MarketDataRequest(record.getStockCode(), record.getMarket()), executedAt);
            if (quote.marketAt().isBefore(executedAt.minusSeconds(QUOTE_MAX_AGE_SECONDS))) {
                throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "모의 주문 처리 중 시세가 지연되었습니다.");
            }
        }
        record.setTradeDate(LocalDateTime.ofInstant(executedAt, clock.getZone()));
        record.setQuoteProvider(quote.provider());
        record.setQuoteMarketAt(utc(quote.marketAt()));
        record.setQuoteReceivedAt(utc(quote.receivedAt()));
    }

    private LocalDateTime utc(Instant at) {
        return at == null ? null : LocalDateTime.ofInstant(at, ZoneOffset.UTC);
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
        return record;
    }

    private PaperTradeResponse tradeResponse(PaperTradeRecord record, boolean usd) {
        return new PaperTradeResponse(
            record.getTradeRecordId(),
            record.getRecommendationId(),
            record.getStockCode(),
            record.getStockName(),
            record.getMarket(),
            record.getTradeType(),
            price(record.getTradePrice(), usd),
            quantity(record.getQuantity()),
            money(tradeAmount(record.getTradePrice(), record.getQuantity(), usd)),
            money(record.getRealizedProfit() == null ? BigDecimal.ZERO : record.getRealizedProfit()),
            record.getTradeDate(),
            record.getMemo(),
            record.getQuoteProvider(),
            record.getQuoteMarketAt() == null ? null : record.getQuoteMarketAt().atOffset(ZoneOffset.UTC),
            record.getQuoteReceivedAt() == null ? null : record.getQuoteReceivedAt().atOffset(ZoneOffset.UTC),
            record.getSignalBasisDate(),
            record.getSignalModelSha256(),
            record.getSignalExpiresAt() == null ? null : record.getSignalExpiresAt().atOffset(ZoneOffset.UTC)
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

    private BigDecimal price(BigDecimal value, boolean usd) {
        return value.setScale(usd ? USD_PRICE_SCALE : MONEY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros();
    }

    private BigDecimal tradeAmount(BigDecimal price, BigDecimal quantity, boolean usd) {
        BigDecimal amount = price.multiply(quantity);
        return usd ? normalizeMoney(amount) : amount;
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

        private void buy(BigDecimal amount, BigDecimal boughtQuantity) {
            quantity = quantity.add(boughtQuantity);
            totalCost = totalCost.add(amount);
        }

        private void sell(BigDecimal soldQuantity, boolean usd) {
            BigDecimal cost = usd ? usCostForSale(soldQuantity) : averagePrice().multiply(soldQuantity);
            totalCost = totalCost.subtract(cost);
            quantity = quantity.subtract(soldQuantity);
            if (quantity.signum() == 0) {
                totalCost = BigDecimal.ZERO;
            }
        }

        private BigDecimal usCostForSale(BigDecimal soldQuantity) {
            return totalCost.multiply(soldQuantity).divide(quantity, MONEY_SCALE, RoundingMode.HALF_UP);
        }

        private BigDecimal averagePrice() {
            return quantity.signum() > 0
                ? totalCost.divide(quantity, 8, RoundingMode.HALF_UP)
                : BigDecimal.ZERO;
        }
    }
}
