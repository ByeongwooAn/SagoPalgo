package com.sagopalgo.api.recommendation.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.recommendation.client.AiAnalysisGateway;
import com.sagopalgo.api.recommendation.dto.DailyInference;
import com.sagopalgo.api.recommendation.dto.DailySignal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

@Service
public class DailySignalService {
    private static final Logger log = LoggerFactory.getLogger(DailySignalService.class);
    private static final Set<String> FEATURES = Set.of(
        "openToClose", "closeReturn1", "closeReturn5", "closeReturn20", "rangeOverOpen", "closeVolatility20", "volumeRatio20"
    );

    private final KisMarketPriceClient kis;
    private final AiAnalysisGateway ai;
    private final AiAnalysisProperties properties;
    private final Clock clock;

    @Autowired
    public DailySignalService(KisMarketPriceClient kis, AiAnalysisGateway ai, AiAnalysisProperties properties) {
        this(kis, ai, properties, Clock.system(KrxDailySignalCalendar.SEOUL));
    }

    DailySignalService(KisMarketPriceClient kis, AiAnalysisGateway ai, AiAnalysisProperties properties, Clock clock) {
        this.kis = kis;
        this.ai = ai;
        this.properties = properties;
        this.clock = clock.withZone(KrxDailySignalCalendar.SEOUL);
    }

    public DailySignal analyze(String stockCode, String market) {
        if (!"KOSPI".equals(market) || !("005930".equals(stockCode) || "000660".equals(stockCode))) return null;
        OffsetDateTime now = OffsetDateTime.now(clock);
        if (!KrxDailySignalCalendar.covers(now.toLocalDate())) {
            return DailySignal.withheld("CALENDAR_UNAVAILABLE", null, now);
        }
        LocalDate basisDate = KrxDailySignalCalendar.latestClosed(now);
        if (basisDate == null) return DailySignal.withheld("CALENDAR_UNAVAILABLE", null, now);
        List<LocalDate> dates = KrxDailySignalCalendar.window(basisDate);
        if (dates.isEmpty()) return DailySignal.withheld("CALENDAR_UNAVAILABLE", basisDate, now);
        OffsetDateTime expiresAt = KrxDailySignalCalendar.nextClose(basisDate);
        if (expiresAt == null) return DailySignal.withheld("CALENDAR_UNAVAILABLE", basisDate, now);
        if (basisDate.equals(now.toLocalDate()) && now.toLocalTime().isBefore(KrxDailySignalCalendar.CHECK_AFTER)) {
            return DailySignal.withheld("BAR_NOT_FINAL", basisDate, now);
        }
        if (!properties.isEnabled()) return DailySignal.withheld("MODEL_UNAVAILABLE", basisDate, now);

        MarketDataRequest request = new MarketDataRequest(stockCode, market);
        LocalDate firstDate = dates.get(0);
        List<StockCandle> candles;
        try {
            candles = kis.rawDailyCandles(request, firstDate, basisDate);
            if (!candles.stream().map(bar -> bar.dateTime().toLocalDate()).toList().equals(dates)
                    || !candles.stream().allMatch(DailySignalService::validBar)) {
                return DailySignal.withheld("BAR_MISSING_OR_INVALID", basisDate, now);
            }
            StockCandle last = candles.get(candles.size() - 1);
            if (kis.rawDailyReference(request, basisDate).filter(reference -> sameValues(last, reference)).isEmpty()) {
                return DailySignal.withheld("BAR_NOT_FINAL", basisDate, now);
            }
        } catch (ApiException exception) {
            log.warn("장 마감 모델 원주가 확인 실패. stockCode={} message={}", stockCode, exception.getMessage());
            return DailySignal.withheld("BAR_MISSING_OR_INVALID", basisDate, now);
        }

        DailyInference.Request input = new DailyInference.Request(stockCode, market, "KIS", "RAW", basisDate,
            candles.stream().map(bar -> new DailyInference.Bar(bar.dateTime().toLocalDate(),
                bar.openPrice(), bar.highPrice(), bar.lowPrice(), bar.closePrice(), bar.volume())).toList());
        var result = ai.inferDaily(input).filter(value -> matches(input, value)).orElse(null);
        OffsetDateTime evaluatedAt = OffsetDateTime.now(clock);
        if (!evaluatedAt.isBefore(expiresAt)) return DailySignal.withheld("SIGNAL_EXPIRED", basisDate, evaluatedAt);
        if (result == null) return DailySignal.withheld("MODEL_UNAVAILABLE", basisDate, evaluatedAt);
        String decision = result.threshold() != null && result.probability() >= result.threshold() ? "BUY_WATCH" : "WAIT";
        return new DailySignal(decision, null, result.modelVersion(), result.modelSha256(), "kis-krx-raw-ohlcv-v1",
            basisDate, firstDate, evaluatedAt, expiresAt, result.probability(), result.threshold(), result.contributions());
    }

    private static boolean validBar(StockCandle bar) {
        return bar.lowPrice().signum() > 0 && bar.volume().signum() > 0
            && bar.lowPrice().compareTo(bar.openPrice().min(bar.closePrice())) <= 0
            && bar.highPrice().compareTo(bar.openPrice().max(bar.closePrice())) >= 0;
    }

    private static boolean sameValues(StockCandle first, StockCandle second) {
        return first.openPrice().compareTo(second.openPrice()) == 0 && first.highPrice().compareTo(second.highPrice()) == 0
            && first.lowPrice().compareTo(second.lowPrice()) == 0 && first.closePrice().compareTo(second.closePrice()) == 0
            && first.volume().compareTo(second.volume()) == 0;
    }

    private static boolean matches(DailyInference.Request request, DailyInference.Result result) {
        return request.stockCode().equals(result.stockCode()) && request.signalDate().equals(result.signalDate())
            && "daily-l2-logistic-v1".equals(result.modelVersion())
            && result.modelSha256() != null && result.modelSha256().matches("[a-f0-9]{64}")
            && isProbability(result.probability()) && (result.threshold() == null || isProbability(result.threshold()))
            && result.contributions() != null && result.contributions().keySet().equals(FEATURES)
            && result.contributions().values().stream().allMatch(value -> value != null && Double.isFinite(value));
    }

    private static boolean isProbability(Double value) {
        return value != null && value >= 0 && value <= 1;
    }
}
