package com.sagopalgo.api.holding.service;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.holding.dto.HoldingCreateResponse;
import com.sagopalgo.api.holding.dto.HoldingRequest;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.dto.PortfolioCostExposure;
import com.sagopalgo.api.holding.dto.PortfolioSummaryResponse;
import com.sagopalgo.api.holding.mapper.HoldingMapper;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.market.model.StockQuote;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 보유 종목 등록/수정/삭제와 포트폴리오 요약 계산을 담당하는 서비스입니다.
 */
@Service
public class HoldingService {

    private static final String DEFAULT_STATUS = "HOLDING";
    private static final int MONEY_SCALE = 2;
    private static final int RATE_SCALE = 2;

    private final HoldingMapper holdingMapper;
    private final CapitalService capitalService;
    private final MarketPriceService marketPriceService;

    public HoldingService(
        HoldingMapper holdingMapper,
        CapitalService capitalService,
        MarketPriceService marketPriceService
    ) {
        this.holdingMapper = holdingMapper;
        this.capitalService = capitalService;
        this.marketPriceService = marketPriceService;
    }

    @Transactional(readOnly = true)
    public HoldingsListResponse findAll(Long userId) {
        List<Holding> holdings = holdingMapper.findActiveByUserId(userId);
        Map<String, StockQuote> quotes = new HashMap<>();
        List<HoldingResponse> items = holdings.stream()
            .map(holding -> {
                String key = holding.getMarket() + ":" + holding.getStockCode();
                StockQuote quote = quotes.computeIfAbsent(key, ignored -> marketPriceService.quote(holding));
                // 대체 매수가는 동일 종목이라도 등록 건별 매수가를 사용합니다.
                if ("FALLBACK".equals(quote.provider())) {
                    quote = new StockQuote("FALLBACK", holding.getStockCode(), holding.getStockName(),
                        holding.getMarket(), holding.getBuyPrice(), null, null, null, null, null, null, null, null);
                }
                return HoldingResponse.from(holding, quote, profitRate(holding, quote.currentPrice()));
            })
            .toList();
        return new HoldingsListResponse(summary(userId, items), items);
    }

    @Transactional(readOnly = true)
    public HoldingResponse findOne(Long userId, Long holdingId) {
        return holdingMapper.findByIdAndUserId(holdingId, userId)
            .map(this::toResponse)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다."));
    }

    @Transactional(readOnly = true)
    public List<Long> findActiveIds(Long userId) {
        return holdingMapper.findActiveIdsByUserId(userId);
    }

    @Transactional(readOnly = true)
    public Holding findRecord(Long userId, Long holdingId) {
        return holdingMapper.findByIdAndUserId(holdingId, userId)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다."));
    }

    @Transactional(readOnly = true)
    public Optional<PortfolioCostExposure> costExposure(Long userId, String stockCode, String market) {
        BigDecimal totalCost = BigDecimal.ZERO;
        BigDecimal stockCost = BigDecimal.ZERO;
        for (Holding holding : holdingMapper.findActiveByUserId(userId)) {
            if (holding.getBuyPrice() == null || holding.getQuantity() == null
                || holding.getBuyPrice().signum() <= 0 || holding.getQuantity().signum() <= 0) {
                continue;
            }
            BigDecimal cost = holding.getBuyPrice().multiply(holding.getQuantity());
            totalCost = totalCost.add(cost);
            if (holding.getStockCode().equals(stockCode) && holding.getMarket().equals(market)) {
                stockCost = stockCost.add(cost);
            }
        }
        if (totalCost.signum() <= 0 || stockCost.signum() <= 0) {
            return Optional.empty();
        }
        BigDecimal portfolioRate = percent(stockCost, totalCost);
        CapitalResponse capital = capitalService.findByUserId(userId);
        if (capital.availableCapital() == null || capital.availableCapital().signum() <= 0) {
            return Optional.of(new PortfolioCostExposure(portfolioRate, null, null));
        }
        return Optional.of(new PortfolioCostExposure(
            portfolioRate,
            percent(stockCost, capital.availableCapital()),
            percent(capital.recommendedMaxPosition(), capital.availableCapital())
        ));
    }

    private BigDecimal percent(BigDecimal numerator, BigDecimal denominator) {
        return numerator.multiply(new BigDecimal("100"))
            .divide(denominator, 12, RoundingMode.HALF_UP);
    }

    @Transactional
    public HoldingCreateResponse create(Long userId, HoldingRequest request) {
        holdingMapper.lockUser(userId);
        rejectImportedDuplicate(userId, null, request);
        Holding holding = buildHolding(userId, request);
        holdingMapper.insert(holding);
        return new HoldingCreateResponse(holding.getHoldingId());
    }

    @Transactional
    public HoldingResponse update(Long userId, Long holdingId, HoldingRequest request) {
        holdingMapper.lockUser(userId);
        Holding existing = findRecord(userId, holdingId);
        if ("KB".equals(existing.getSource())) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "KB 보유분은 KB에서 다시 불러와 갱신하세요. 직접 수정하려면 삭제 후 수동 등록하세요.");
        }
        rejectImportedDuplicate(userId, holdingId, request);
        Holding holding = buildHolding(userId, request);
        holding.setHoldingId(holdingId);

        int updatedRows = holdingMapper.updateByIdAndUserId(holding);
        if (updatedRows == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다.");
        }

        return holdingMapper.findByIdAndUserId(holdingId, userId)
            .map(this::toResponse)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다."));
    }

    @Transactional
    public void delete(Long userId, Long holdingId) {
        holdingMapper.lockUser(userId);
        int deletedRows = holdingMapper.deleteByIdAndUserId(holdingId, userId);
        if (deletedRows == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다.");
        }
    }

    private Holding buildHolding(Long userId, HoldingRequest request) {
        Holding holding = new Holding();
        holding.setUserId(userId);
        holding.setStockCode(request.stockCode().trim());
        holding.setStockName(request.stockName().trim());
        holding.setMarket(request.market().trim().toUpperCase(java.util.Locale.ROOT));
        holding.setBuyPrice(normalizeMoney(request.buyPrice()));
        holding.setQuantity(request.quantity());
        holding.setBuyDate(request.buyDate());
        holding.setStopLossRate(request.stopLossRate());
        holding.setTakeProfitRate(request.takeProfitRate());
        holding.setStatus(DEFAULT_STATUS);
        return holding;
    }

    private void rejectImportedDuplicate(Long userId, Long holdingId, HoldingRequest request) {
        boolean duplicate = holdingMapper.findActiveByUserId(userId).stream()
            .anyMatch(holding -> "KB".equals(holding.getSource())
                && !holding.getHoldingId().equals(holdingId)
                && holding.getStockCode().equals(request.stockCode().trim())
                && java.util.Set.of("KOSPI", "KOSDAQ", "KONEX", "KRX", "KR", "KR_ETC")
                    .contains(request.market().trim().toUpperCase(java.util.Locale.ROOT)));
        if (duplicate) throw new ApiException(ErrorCode.VALIDATION_ERROR,
            "같은 종목의 KB 보유분이 있습니다. 이중 계산을 피하려면 기존 KB 보유분을 먼저 정리하세요.");
    }

    private HoldingResponse toResponse(Holding holding) {
        StockQuote quote = marketPriceService.quote(holding);
        return HoldingResponse.from(holding, quote, profitRate(holding, quote.currentPrice()));
    }

    private PortfolioSummaryResponse summary(Long userId, List<HoldingResponse> holdings) {
        BigDecimal totalInvestment = BigDecimal.ZERO;
        BigDecimal totalProfit = BigDecimal.ZERO;

        for (HoldingResponse holding : holdings) {
            BigDecimal currentPrice = holding.currentPrice();
            BigDecimal quantity = holding.quantity();
            BigDecimal investment = holding.buyPrice().multiply(quantity);
            BigDecimal valuation = currentPrice.multiply(quantity);

            totalInvestment = totalInvestment.add(investment);
            totalProfit = totalProfit.add(valuation.subtract(investment));
        }

        BigDecimal profitRate = BigDecimal.ZERO;
        if (totalInvestment.compareTo(BigDecimal.ZERO) > 0) {
            profitRate = totalProfit
                .divide(totalInvestment, 6, RoundingMode.HALF_UP)
                .multiply(new BigDecimal("100"))
                .setScale(RATE_SCALE, RoundingMode.HALF_UP);
        }

        BigDecimal maxAllowedLoss = capitalService.maxAllowedLoss(userId);
        BigDecimal riskUsageRate = BigDecimal.ZERO;
        if (totalProfit.signum() < 0 && maxAllowedLoss.signum() > 0) {
            riskUsageRate = totalProfit.abs()
                .divide(maxAllowedLoss, 6, RoundingMode.HALF_UP)
                .setScale(4, RoundingMode.HALF_UP);
        }

        return new PortfolioSummaryResponse(
            totalProfit.setScale(MONEY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros(),
            profitRate.stripTrailingZeros(),
            maxAllowedLoss.stripTrailingZeros(),
            riskUsageRate.stripTrailingZeros()
        );
    }

    private BigDecimal profitRate(Holding holding, BigDecimal currentPrice) {
        return currentPrice.subtract(holding.getBuyPrice())
            .divide(holding.getBuyPrice(), 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"))
            .setScale(RATE_SCALE, RoundingMode.HALF_UP);
    }

    private BigDecimal normalizeMoney(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }
}
