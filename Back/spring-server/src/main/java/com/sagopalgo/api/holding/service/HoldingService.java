package com.sagopalgo.api.holding.service;

import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.holding.dto.HoldingCreateResponse;
import com.sagopalgo.api.holding.dto.HoldingRequest;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.dto.PortfolioSummaryResponse;
import com.sagopalgo.api.holding.mapper.HoldingMapper;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.service.MarketPriceService;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
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
        List<HoldingResponse> items = holdings.stream()
            .map(this::toResponse)
            .toList();
        return new HoldingsListResponse(summary(userId, holdings), items);
    }

    @Transactional
    public HoldingCreateResponse create(Long userId, HoldingRequest request) {
        Holding holding = buildHolding(userId, request);
        holdingMapper.insert(holding);
        return new HoldingCreateResponse(holding.getHoldingId());
    }

    @Transactional
    public HoldingResponse update(Long userId, Long holdingId, HoldingRequest request) {
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
        int deletedRows = holdingMapper.deleteByIdAndUserId(holdingId, userId);
        if (deletedRows == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "보유 종목을 찾을 수 없습니다.");
        }
    }

    private Holding buildHolding(Long userId, HoldingRequest request) {
        Holding holding = new Holding();
        holding.setUserId(userId);
        holding.setStockCode(request.stockCode());
        holding.setStockName(request.stockName());
        holding.setMarket(request.market());
        holding.setBuyPrice(normalizeMoney(request.buyPrice()));
        holding.setQuantity(request.quantity());
        holding.setBuyDate(request.buyDate());
        holding.setStopLossRate(request.stopLossRate());
        holding.setTakeProfitRate(request.takeProfitRate());
        holding.setStatus(DEFAULT_STATUS);
        return holding;
    }

    private HoldingResponse toResponse(Holding holding) {
        BigDecimal currentPrice = currentPrice(holding);
        return HoldingResponse.from(holding, currentPrice, profitRate(holding, currentPrice));
    }

    private PortfolioSummaryResponse summary(Long userId, List<Holding> holdings) {
        BigDecimal totalInvestment = BigDecimal.ZERO;
        BigDecimal totalProfit = BigDecimal.ZERO;

        for (Holding holding : holdings) {
            BigDecimal currentPrice = currentPrice(holding);
            BigDecimal quantity = holding.getQuantity();
            BigDecimal investment = holding.getBuyPrice().multiply(quantity);
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

        return new PortfolioSummaryResponse(
            totalProfit.setScale(MONEY_SCALE, RoundingMode.HALF_UP).stripTrailingZeros(),
            profitRate.stripTrailingZeros(),
            capitalService.maxAllowedLoss(userId).stripTrailingZeros(),
            BigDecimal.ZERO.setScale(RATE_SCALE, RoundingMode.HALF_UP).stripTrailingZeros()
        );
    }

    private BigDecimal profitRate(Holding holding, BigDecimal currentPrice) {
        return currentPrice.subtract(holding.getBuyPrice())
            .divide(holding.getBuyPrice(), 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"))
            .setScale(RATE_SCALE, RoundingMode.HALF_UP);
    }

    private BigDecimal currentPrice(Holding holding) {
        return marketPriceService.currentPrice(holding);
    }

    private BigDecimal normalizeMoney(BigDecimal value) {
        return value.setScale(MONEY_SCALE, RoundingMode.HALF_UP);
    }
}
