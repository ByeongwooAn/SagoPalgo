package com.sagopalgo.api.alert.service;

import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.alert.model.PortfolioPosition;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 종목별 보유 비중과 포트폴리오 전체 손실 한도를 평가합니다.
 */
@Service
public class PortfolioRiskAlertService {

    private final AlertMapper alertMapper;
    private final WatchlistMapper watchlistMapper;
    private final CapitalService capitalService;
    private final AlertProperties properties;

    public PortfolioRiskAlertService(
        AlertMapper alertMapper,
        WatchlistMapper watchlistMapper,
        CapitalService capitalService,
        AlertProperties properties
    ) {
        this.alertMapper = alertMapper;
        this.watchlistMapper = watchlistMapper;
        this.capitalService = capitalService;
        this.properties = properties;
    }

    @Transactional
    public int createAlerts(Long userId, List<PortfolioPosition> positions) {
        if (!properties.isPortfolioEventsEnabled() || userId == null || positions == null || positions.isEmpty()) {
            return 0;
        }

        CapitalResponse capital = capitalService.findByUserId(userId);
        if (capital.availableCapital() == null || capital.availableCapital().signum() <= 0) {
            return 0;
        }

        int created = 0;
        for (PortfolioPosition position : positions) {
            created += createOverweightAlert(capital, position);
        }
        created += createTotalLossAlert(userId, capital, positions);
        return created;
    }

    private int createOverweightAlert(CapitalResponse capital, PortfolioPosition position) {
        if (!valid(position) || capital.recommendedMaxPosition() == null
            || capital.recommendedMaxPosition().signum() <= 0) {
            return 0;
        }
        Holding holding = position.holding();
        if (!holdingAlertsEnabled(holding)) {
            return 0;
        }

        BigDecimal positionAmount = position.quote().currentPrice().multiply(holding.getQuantity());
        if (positionAmount.compareTo(capital.recommendedMaxPosition()) <= 0) {
            return 0;
        }
        if (existsRecentHoldingEvent(holding, "PORTFOLIO_POSITION_OVERWEIGHT")) {
            return 0;
        }

        BigDecimal weightRate = positionAmount
            .divide(capital.availableCapital(), 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"));
        return insert(
            holding.getUserId(),
            "PORTFOLIO_POSITION_OVERWEIGHT",
            holding.getStockCode(),
            holding.getMarket(),
            holding.getStockName() + " 보유 비중 초과",
            "평가금액 %s원으로 자본금의 %s%%이며 종목당 권장 한도 %s원을 넘었습니다."
                .formatted(money(positionAmount), rate(weightRate), money(capital.recommendedMaxPosition()))
        );
    }

    private int createTotalLossAlert(
        Long userId,
        CapitalResponse capital,
        List<PortfolioPosition> positions
    ) {
        if (capital.riskPerTradeRate() == null) {
            return 0;
        }
        BigDecimal maxAllowedLoss = capital.availableCapital().multiply(capital.riskPerTradeRate());
        if (maxAllowedLoss.signum() <= 0) {
            return 0;
        }

        BigDecimal totalProfit = positions.stream()
            .filter(this::valid)
            .filter(position -> !isFallback(position.quote()))
            .map(this::profitAmount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);
        if (totalProfit.signum() >= 0 || totalProfit.abs().compareTo(maxAllowedLoss) < 0) {
            return 0;
        }

        LocalDateTime cutoff = cooldownCutoff();
        if (alertMapper.existsRecentPortfolioEvent(userId, "PORTFOLIO_TOTAL_LOSS", cutoff)) {
            return 0;
        }
        BigDecimal usageRate = totalProfit.abs()
            .divide(maxAllowedLoss, 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"));
        return insert(
            userId,
            "PORTFOLIO_TOTAL_LOSS",
            null,
            null,
            "포트폴리오 손실 한도 초과",
            "현재 미실현 손실 %s원으로 허용 손실 %s원의 %s%%를 사용했습니다."
                .formatted(money(totalProfit.abs()), money(maxAllowedLoss), rate(usageRate))
        );
    }

    private BigDecimal profitAmount(PortfolioPosition position) {
        Holding holding = position.holding();
        return position.quote().currentPrice()
            .subtract(holding.getBuyPrice())
            .multiply(holding.getQuantity());
    }

    private boolean existsRecentHoldingEvent(Holding holding, String eventType) {
        return alertMapper.existsRecentEvent(
            holding.getUserId(),
            holding.getStockCode(),
            holding.getMarket(),
            eventType,
            cooldownCutoff()
        );
    }

    private boolean holdingAlertsEnabled(Holding holding) {
        return watchlistMapper.findAlertEnabledByUserStockAndMarket(
            holding.getUserId(),
            holding.getStockCode(),
            holding.getMarket()
        ).orElse(true);
    }

    private int insert(
        Long userId,
        String eventType,
        String stockCode,
        String market,
        String title,
        String body
    ) {
        AlertRecord record = new AlertRecord();
        record.setUserId(userId);
        record.setAlertType("PORTFOLIO");
        record.setEventType(eventType);
        record.setStockCode(stockCode);
        record.setMarket(market);
        record.setTitle(limit(title, 100));
        record.setBody(limit(body, 500));
        return alertMapper.insertEvent(record) > 0 ? 1 : 0;
    }

    private boolean valid(PortfolioPosition position) {
        return position != null
            && position.holding() != null
            && position.quote() != null
            && position.quote().currentPrice() != null
            && position.quote().currentPrice().signum() > 0
            && position.holding().getBuyPrice() != null
            && position.holding().getQuantity() != null
            && position.holding().getQuantity().signum() > 0;
    }

    private boolean isFallback(StockQuote quote) {
        return "FALLBACK".equalsIgnoreCase(quote.provider());
    }

    private LocalDateTime cooldownCutoff() {
        return LocalDateTime.now().minusMinutes(Math.max(1, properties.getCooldownMinutes()));
    }

    private String money(BigDecimal value) {
        return value.setScale(0, RoundingMode.HALF_UP).toPlainString();
    }

    private String rate(BigDecimal value) {
        return value.setScale(2, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString();
    }

    private String limit(String value, int maxLength) {
        String trimmed = value == null ? "" : value.trim();
        return trimmed.length() <= maxLength ? trimmed : trimmed.substring(0, maxLength);
    }
}
