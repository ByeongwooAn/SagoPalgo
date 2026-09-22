package com.sagopalgo.api.alert.service;

import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.ChronoUnit;
import java.util.HexFormat;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 현재가 조건과 새 뉴스·공시를 추천과 독립된 Windows 알림으로 변환합니다.
 */
@Service
public class EventAlertService {

    private final AlertMapper alertMapper;
    private final WatchlistMapper watchlistMapper;
    private final AlertProperties properties;

    public EventAlertService(
        AlertMapper alertMapper,
        WatchlistMapper watchlistMapper,
        AlertProperties properties
    ) {
        this.alertMapper = alertMapper;
        this.watchlistMapper = watchlistMapper;
        this.properties = properties;
    }

    @Transactional
    public int createPriceAlerts(Holding holding, StockQuote quote) {
        if (!properties.isPriceEventsEnabled() || quote == null || isFallback(quote)) {
            return 0;
        }
        if (!holdingAlertsEnabled(holding)) {
            return 0;
        }

        int created = 0;
        BigDecimal profitRate = profitRate(holding, quote.currentPrice());
        if (holding.getStopLossRate() != null && profitRate.compareTo(holding.getStopLossRate()) <= 0) {
            created += createPriceEvent(
                holding,
                "PRICE_STOP_LOSS",
                "RISK",
                holding.getStockName() + " 손절 기준 도달",
                "현재 수익률 %s%%로 손절 기준 %s%%에 도달했습니다."
                    .formatted(decimal(profitRate), decimal(holding.getStopLossRate()))
            );
        }
        if (holding.getTakeProfitRate() != null && profitRate.compareTo(holding.getTakeProfitRate()) >= 0) {
            created += createPriceEvent(
                holding,
                "PRICE_TAKE_PROFIT",
                "SELL",
                holding.getStockName() + " 익절 기준 도달",
                "현재 수익률 %s%%로 익절 기준 %s%%에 도달했습니다."
                    .formatted(decimal(profitRate), decimal(holding.getTakeProfitRate()))
            );
        }

        BigDecimal changeRate = valueOrZero(quote.changeRate());
        BigDecimal volatility = valueOrZero(properties.getVolatilityThresholdRate()).abs();
        if (volatility.signum() > 0 && changeRate.compareTo(volatility) >= 0) {
            created += createPriceEvent(
                holding,
                "PRICE_SURGE",
                "PRICE",
                holding.getStockName() + " 급등 감지",
                "오늘 등락률이 +%s%%로 급등 기준 %s%%를 넘었습니다."
                    .formatted(decimal(changeRate), decimal(volatility))
            );
        }
        if (volatility.signum() > 0 && changeRate.compareTo(volatility.negate()) <= 0) {
            created += createPriceEvent(
                holding,
                "PRICE_DROP",
                "RISK",
                holding.getStockName() + " 급락 감지",
                "오늘 등락률이 %s%%로 급락 기준 -%s%%를 넘었습니다."
                    .formatted(decimal(changeRate), decimal(volatility))
            );
        }
        return created;
    }

    @Transactional
    public int createResearchAlerts(
        Long userId,
        String stockCode,
        String stockName,
        List<NewsArticle> news,
        List<Disclosure> disclosures
    ) {
        if (!properties.isResearchEventsEnabled() || !researchAlertsEnabled(userId, stockCode)) {
            return 0;
        }

        int created = 0;
        Instant newsCutoff = Instant.now().minus(
            Math.max(1, properties.getNewsMaxAgeHours()),
            ChronoUnit.HOURS
        );
        for (NewsArticle article : news) {
            if (article == null || article.publishedAt() == null || article.publishedAt().isBefore(newsCutoff)) {
                continue;
            }
            created += insertEvent(
                userId,
                "NEWS",
                eventKey("NEWS", stockCode, newsIdentity(article)),
                "NEWS",
                stockCode,
                null,
                stockName + " 새 뉴스",
                article.title()
            );
        }

        LocalDate disclosureCutoff = LocalDate.now().minusDays(
            Math.max(0, properties.getDisclosureMaxAgeDays())
        );
        for (Disclosure disclosure : disclosures) {
            if (disclosure == null || disclosure.receiptDate() == null
                || disclosure.receiptDate().isBefore(disclosureCutoff)
                || disclosure.receiptNumber() == null
                || disclosure.receiptNumber().isBlank()) {
                continue;
            }
            created += insertEvent(
                userId,
                "DISCLOSURE",
                eventKey("DISCLOSURE", stockCode, disclosure.receiptNumber()),
                "DISCLOSURE",
                stockCode,
                null,
                stockName + " 새 공시",
                disclosure.reportName()
            );
        }
        return created;
    }

    private int createPriceEvent(
        Holding holding,
        String eventType,
        String alertType,
        String title,
        String body
    ) {
        LocalDateTime cutoff = LocalDateTime.now().minusMinutes(
            Math.max(1, properties.getCooldownMinutes())
        );
        if (alertMapper.existsRecentEvent(
            holding.getUserId(),
            holding.getStockCode(),
            holding.getMarket(),
            eventType,
            cutoff
        )) {
            return 0;
        }
        return insertEvent(
            holding.getUserId(),
            eventType,
            null,
            alertType,
            holding.getStockCode(),
            holding.getMarket(),
            title,
            body
        );
    }

    private int insertEvent(
        Long userId,
        String eventType,
        String eventKey,
        String alertType,
        String stockCode,
        String market,
        String title,
        String body
    ) {
        AlertRecord record = new AlertRecord();
        record.setUserId(userId);
        record.setAlertType(alertType);
        record.setEventType(eventType);
        record.setEventKey(eventKey);
        record.setStockCode(stockCode);
        record.setMarket(market);
        record.setTitle(limit(title, 100));
        record.setBody(limit(body, 500));
        return alertMapper.insertEvent(record) > 0 ? 1 : 0;
    }

    private boolean holdingAlertsEnabled(Holding holding) {
        return watchlistMapper.findAlertEnabledByUserStockAndMarket(
            holding.getUserId(),
            holding.getStockCode(),
            holding.getMarket()
        ).orElse(true);
    }

    private boolean researchAlertsEnabled(Long userId, String stockCode) {
        return watchlistMapper.findAlertEnabledByUserAndStockCode(userId, stockCode).orElse(false);
    }

    private BigDecimal profitRate(Holding holding, BigDecimal currentPrice) {
        if (holding.getBuyPrice() == null || holding.getBuyPrice().signum() <= 0 || currentPrice == null) {
            return BigDecimal.ZERO;
        }
        return currentPrice.subtract(holding.getBuyPrice())
            .divide(holding.getBuyPrice(), 6, RoundingMode.HALF_UP)
            .multiply(new BigDecimal("100"))
            .setScale(2, RoundingMode.HALF_UP);
    }

    private boolean isFallback(StockQuote quote) {
        return "FALLBACK".equalsIgnoreCase(quote.provider());
    }

    private String newsIdentity(NewsArticle article) {
        if (article.link() != null && !article.link().isBlank()) {
            return article.provider() + "|" + article.link();
        }
        return article.provider() + "|" + article.title() + "|" + article.publishedAt();
    }

    private String eventKey(String eventType, String stockCode, String identity) {
        String source = eventType + "|" + stockCode + "|" + identity;
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(source.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 알고리즘을 사용할 수 없습니다.", exception);
        }
    }

    private BigDecimal valueOrZero(BigDecimal value) {
        return value == null ? BigDecimal.ZERO : value;
    }

    private String decimal(BigDecimal value) {
        return value.stripTrailingZeros().toPlainString();
    }

    private String limit(String value, int maxLength) {
        if (value == null || value.isBlank()) {
            return "새 투자 이벤트가 감지되었습니다. 앱에서 상세 내용을 확인하세요.";
        }
        String trimmed = value.trim();
        return trimmed.length() <= maxLength ? trimmed : trimmed.substring(0, maxLength);
    }
}
