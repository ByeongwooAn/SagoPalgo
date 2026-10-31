package com.sagopalgo.api.order.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.dto.KbBalanceItemResponse;
import com.sagopalgo.api.kb.service.KbAccountService;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.order.client.KbLimitOrderContract;
import com.sagopalgo.api.order.dto.OrderPrecheckHistoryItemResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckHistoryResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderPrecheckResponse;
import com.sagopalgo.api.order.dto.OrderSafetyCheckResponse;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 주문안을 계좌 자원과 안전 한도에 대조하되 실제 증권사 주문은 호출하지 않습니다.
 */
@Service
public class OrderPrecheckService {

    private static final BigDecimal ONE_HUNDRED = new BigDecimal("100");
    private static final int MONEY_SCALE = 2;
    private static final int QUANTITY_SCALE = 4;
    private static final int RATE_SCALE = 2;
    private static final int MAX_HISTORY_LIMIT = 100;
    private static final String SUBMISSION_MESSAGE = "사전검증은 주문을 전송하지 않습니다. 승인 기록과 별도의 실제 전송 확인이 필요합니다.";

    private final OrderPrecheckMapper mapper;
    private final KbAccountService kbAccountService;
    private final MarketPriceService marketPriceService;
    private final Provider kbProperties;

    public OrderPrecheckService(
        OrderPrecheckMapper mapper,
        KbAccountService kbAccountService,
        MarketPriceService marketPriceService,
        SecuritiesProviderProperties securitiesProviderProperties
    ) {
        this.mapper = mapper;
        this.kbAccountService = kbAccountService;
        this.marketPriceService = marketPriceService;
        this.kbProperties = securitiesProviderProperties.getKb();
    }

    @Transactional
    public OrderPrecheckResponse precheck(Long userId, OrderPrecheckRequest request) {
        String side = request.side().trim().toUpperCase(Locale.ROOT);
        String stockCode = request.stockCode().trim();
        String stockName = request.stockName().trim();
        String market = request.market().trim().toUpperCase(Locale.ROOT);
        BigDecimal limitPrice = money(request.limitPrice());
        BigDecimal quantity = quantity(request.quantity());
        BigDecimal estimatedAmount = money(limitPrice.multiply(quantity));
        BigDecimal maxOrderAmount = positiveOrDefault(kbProperties.getMaxOrderAmount(), new BigDecimal("1000000"));
        BigDecimal maxDeviationRate = positiveOrDefault(kbProperties.getMaxPriceDeviationRate(), new BigDecimal("5"));
        List<OrderSafetyCheckResponse> checks = new ArrayList<>();

        addCheck(
            checks,
            "ORDER_SWITCH",
            "주문 스위치",
            kbProperties.isOrderEnabled(),
            kbProperties.isOrderEnabled() ? "KB 주문 기능이 활성화되어 있습니다." : "KB 주문 기능이 OFF입니다."
        );
        boolean accountEnabled = kbProperties.isAccountEnabled();
        addCheck(
            checks,
            "KB_ACCOUNT",
            "KB 계좌 연결",
            accountEnabled,
            accountEnabled ? "KB 계좌 조회가 활성화되어 있습니다." : "KB 계좌 조회 설정이 필요합니다."
        );
        boolean supportedMarket = List.of("KOSPI", "KOSDAQ").contains(market);
        addCheck(
            checks,
            "SUPPORTED_MARKET",
            "주문 시장",
            supportedMarket,
            supportedMarket ? "KB 국내주식 주문 대상 시장입니다." : "현재 주문 준비는 KOSPI/KOSDAQ만 지원합니다."
        );
        boolean orderFormatSupported = KbLimitOrderContract.isSupported(request);
        addCheck(
            checks,
            "KB_ORDER_FORMAT",
            "KB 지정가 주문 형식",
            orderFormatSupported,
            orderFormatSupported
                ? "종목코드, 지정가와 수량이 KB 주문 필드 범위에 맞습니다."
                : "6자리 종목코드와 9자리 이하 정수 원화 지정가·10자리 이하 정수 주식 수량이 필요합니다."
        );
        addCheck(
            checks,
            "MAX_ORDER_AMOUNT",
            "1회 주문 한도",
            estimatedAmount.compareTo(maxOrderAmount) <= 0,
            estimatedAmount.compareTo(maxOrderAmount) <= 0
                ? "예상 주문금액이 1회 한도 이내입니다."
                : "예상 주문금액이 1회 최대 주문금액을 초과합니다."
        );

        QuoteResult quoteResult = quote(stockCode, market);
        addCheck(
            checks,
            "REAL_PRICE",
            "현재가 확인",
            quoteResult.available,
            quoteResult.available
                ? quoteResult.provider + " 현재가를 확인했습니다."
                : quoteResult.message
        );
        BigDecimal deviationRate = deviationRate(limitPrice, quoteResult.currentPrice);
        boolean deviationPassed = quoteResult.available && deviationRate.compareTo(maxDeviationRate) <= 0;
        addCheck(
            checks,
            "PRICE_DEVIATION",
            "지정가 이탈률",
            deviationPassed,
            deviationPassed
                ? "지정가가 현재가 대비 허용 범위 안입니다."
                : "지정가가 현재가 대비 허용 범위를 벗어났습니다."
        );

        BigDecimal orderAvailableCash = BigDecimal.ZERO;
        BigDecimal orderableQuantity = BigDecimal.ZERO;
        if ("BUY".equals(side)) {
            AccountCheck accountCheck = buyAccountCheck(accountEnabled, estimatedAmount);
            orderAvailableCash = accountCheck.availableValue;
            addCheck(checks, "BUYING_POWER", "주문가능현금", accountCheck.passed, accountCheck.message);
        } else {
            AccountCheck accountCheck = sellAccountCheck(accountEnabled, stockCode, quantity);
            orderableQuantity = accountCheck.availableValue;
            addCheck(checks, "SELLABLE_QUANTITY", "주문가능수량", accountCheck.passed, accountCheck.message);
        }

        boolean eligible = checks.stream().allMatch(OrderSafetyCheckResponse::passed);
        String blockerSummary = checks.stream()
            .filter(check -> !check.passed())
            .map(check -> check.label() + ": " + check.message())
            .collect(java.util.stream.Collectors.joining(" | "));
        LocalDateTime checkedAt = LocalDateTime.now();
        OrderPrecheckRecord record = record(
            userId,
            stockCode,
            stockName,
            market,
            side,
            limitPrice,
            quantity,
            estimatedAmount,
            quoteResult,
            orderAvailableCash,
            orderableQuantity,
            eligible,
            blockerSummary,
            checkedAt
        );
        mapper.insert(record);

        return new OrderPrecheckResponse(
            record.getOrderPrecheckId(),
            stockCode,
            stockName,
            market,
            side,
            "LIMIT",
            limitPrice,
            quantity,
            estimatedAmount,
            quoteResult.provider,
            money(quoteResult.currentPrice),
            rate(deviationRate),
            money(orderAvailableCash),
            quantity(orderableQuantity),
            money(maxOrderAmount),
            rate(maxDeviationRate),
            kbProperties.isOrderEnabled(),
            eligible,
            false,
            SUBMISSION_MESSAGE,
            List.copyOf(checks),
            checkedAt
        );
    }

    @Transactional(readOnly = true)
    public OrderPrecheckHistoryResponse history(Long userId, int limit) {
        int safeLimit = Math.max(1, Math.min(limit, MAX_HISTORY_LIMIT));
        List<OrderPrecheckHistoryItemResponse> items = mapper.findRecentByUserId(userId, safeLimit)
            .stream()
            .map(this::historyItem)
            .toList();
        return new OrderPrecheckHistoryResponse(items);
    }

    private QuoteResult quote(String stockCode, String market) {
        try {
            StockQuote quote = marketPriceService.quoteMarket(new MarketDataRequest(stockCode, market));
            BigDecimal currentPrice = quote.currentPrice() == null ? BigDecimal.ZERO : quote.currentPrice();
            String provider = quote.provider() == null ? "FALLBACK" : quote.provider();
            boolean available = currentPrice.signum() > 0 && !"FALLBACK".equalsIgnoreCase(provider);
            return new QuoteResult(
                provider,
                currentPrice,
                available,
                available ? "" : "실제 현재가를 확인할 수 없습니다."
            );
        } catch (ApiException exception) {
            return new QuoteResult("FALLBACK", BigDecimal.ZERO, false, exception.getMessage());
        }
    }

    private AccountCheck buyAccountCheck(boolean accountEnabled, BigDecimal amount) {
        if (!accountEnabled) {
            return new AccountCheck(BigDecimal.ZERO, false, "KB 계좌 조회 설정이 꺼져 있습니다.");
        }
        try {
            BigDecimal availableCash = kbAccountService.settlementBalance().summary().orderAvailableCash();
            boolean passed = availableCash.compareTo(amount) >= 0;
            return new AccountCheck(
                availableCash,
                passed,
                passed ? "예상 주문금액을 충당할 수 있습니다." : "KB 주문가능현금이 부족합니다."
            );
        } catch (ApiException exception) {
            return new AccountCheck(BigDecimal.ZERO, false, exception.getMessage());
        }
    }

    private AccountCheck sellAccountCheck(boolean accountEnabled, String stockCode, BigDecimal requestedQuantity) {
        if (!accountEnabled) {
            return new AccountCheck(BigDecimal.ZERO, false, "KB 계좌 조회 설정이 꺼져 있습니다.");
        }
        try {
            BigDecimal availableQuantity = kbAccountService.executionBalance().items().stream()
                .filter(item -> sameStockCode(item, stockCode))
                .map(KbBalanceItemResponse::orderableQuantity)
                .findFirst()
                .orElse(BigDecimal.ZERO);
            boolean passed = availableQuantity.compareTo(requestedQuantity) >= 0;
            return new AccountCheck(
                availableQuantity,
                passed,
                passed ? "요청 수량을 매도할 수 있습니다." : "KB 주문가능수량이 부족합니다."
            );
        } catch (ApiException exception) {
            return new AccountCheck(BigDecimal.ZERO, false, exception.getMessage());
        }
    }

    private boolean sameStockCode(KbBalanceItemResponse item, String requestedStockCode) {
        return normalizedStockCode(item.stockCode()).equals(normalizedStockCode(requestedStockCode));
    }

    private String normalizedStockCode(String value) {
        if (value == null) {
            return "";
        }
        String normalized = value.replaceAll("[^0-9A-Za-z]", "").toUpperCase(Locale.ROOT);
        if (normalized.length() == 7 && normalized.startsWith("A")) {
            return normalized.substring(1);
        }
        return normalized;
    }

    private BigDecimal deviationRate(BigDecimal requestedPrice, BigDecimal currentPrice) {
        if (currentPrice == null || currentPrice.signum() <= 0) {
            return BigDecimal.ZERO;
        }
        return requestedPrice.subtract(currentPrice).abs()
            .divide(currentPrice, 8, RoundingMode.HALF_UP)
            .multiply(ONE_HUNDRED);
    }

    private void addCheck(
        List<OrderSafetyCheckResponse> checks,
        String code,
        String label,
        boolean passed,
        String message
    ) {
        checks.add(new OrderSafetyCheckResponse(code, label, passed, message));
    }

    private OrderPrecheckRecord record(
        Long userId,
        String stockCode,
        String stockName,
        String market,
        String side,
        BigDecimal limitPrice,
        BigDecimal quantity,
        BigDecimal estimatedAmount,
        QuoteResult quote,
        BigDecimal orderAvailableCash,
        BigDecimal orderableQuantity,
        boolean eligible,
        String blockerSummary,
        LocalDateTime checkedAt
    ) {
        OrderPrecheckRecord record = new OrderPrecheckRecord();
        record.setUserId(userId);
        record.setStockCode(stockCode);
        record.setStockName(stockName);
        record.setMarket(market);
        record.setOrderSide(side);
        record.setOrderType("LIMIT");
        record.setRequestedPrice(limitPrice);
        record.setQuantity(quantity);
        record.setEstimatedAmount(estimatedAmount);
        record.setQuoteProvider(quote.provider);
        record.setCurrentPrice(money(quote.currentPrice));
        record.setOrderAvailableCash(money(orderAvailableCash));
        record.setOrderableQuantity(quantity(orderableQuantity));
        record.setOrderEnabled(kbProperties.isOrderEnabled());
        record.setEligible(eligible);
        record.setBlockerSummary(blockerSummary);
        record.setCreatedAt(checkedAt);
        return record;
    }

    private OrderPrecheckHistoryItemResponse historyItem(OrderPrecheckRecord record) {
        return new OrderPrecheckHistoryItemResponse(
            record.getOrderPrecheckId(),
            record.getStockCode(),
            record.getStockName(),
            record.getMarket(),
            record.getOrderSide(),
            money(record.getRequestedPrice()),
            quantity(record.getQuantity()),
            money(record.getEstimatedAmount()),
            record.getQuoteProvider(),
            money(record.getCurrentPrice()),
            record.isOrderEnabled(),
            record.isEligible(),
            record.getBlockerSummary(),
            record.getCreatedAt()
        );
    }

    private BigDecimal positiveOrDefault(BigDecimal value, BigDecimal fallback) {
        return value == null || value.signum() <= 0 ? fallback : value;
    }

    private BigDecimal money(BigDecimal value) {
        return (value == null ? BigDecimal.ZERO : value)
            .setScale(MONEY_SCALE, RoundingMode.HALF_UP)
            .stripTrailingZeros();
    }

    private BigDecimal quantity(BigDecimal value) {
        return (value == null ? BigDecimal.ZERO : value)
            .setScale(QUANTITY_SCALE, RoundingMode.HALF_UP)
            .stripTrailingZeros();
    }

    private BigDecimal rate(BigDecimal value) {
        return (value == null ? BigDecimal.ZERO : value)
            .setScale(RATE_SCALE, RoundingMode.HALF_UP)
            .stripTrailingZeros();
    }

    private record QuoteResult(
        String provider,
        BigDecimal currentPrice,
        boolean available,
        String message
    ) {
    }

    private record AccountCheck(
        BigDecimal availableValue,
        boolean passed,
        String message
    ) {
    }
}
