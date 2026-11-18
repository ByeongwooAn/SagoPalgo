package com.sagopalgo.api.recommendation.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.config.AiAnalysisProperties;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockCandle;
import com.sagopalgo.api.recommendation.client.AiAnalysisGateway;
import com.sagopalgo.api.recommendation.dto.DailyInference;
import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;

class DailySignalServiceTest {
    private final KisMarketPriceClient kis = mock(KisMarketPriceClient.class);
    private final AiAnalysisGateway ai = mock(AiAnalysisGateway.class);

    @Test
    void leavesOpenSessionOutOfFeatureWindowAndUsesSpecialCloseToExpire() {
        LocalDate basis = LocalDate.parse("2026-11-18");
        stubValidInput("005930", basis, 0.525, 0.525);
        var signal = service("2026-11-19T16:29:59+09:00").analyze("005930", "KOSPI");

        assertThat(signal.basisDate()).isEqualTo(basis);
        assertThat(signal.decision()).isEqualTo("BUY_WATCH");
        assertThat(signal.expiresAt()).isEqualTo(OffsetDateTime.parse("2026-11-19T16:30:00+09:00"));
        ArgumentCaptor<DailyInference.Request> captured = ArgumentCaptor.forClass(DailyInference.Request.class);
        verify(ai).inferDaily(captured.capture());
        assertThat(captured.getValue().priceBasis()).isEqualTo("RAW");
        assertThat(captured.getValue().provider()).isEqualTo("KIS");
        assertThat(captured.getValue().bars()).hasSize(21)
            .allSatisfy(bar -> assertThat(bar.businessDate()).isBeforeOrEqualTo(basis));
    }

    @Test
    void waitsBetweenRegularCloseAndEveningConfirmation() {
        var signal = service("2026-11-19T16:30:00+09:00").analyze("005930", "KOSPI");
        assertThat(signal.holdReason()).isEqualTo("BAR_NOT_FINAL");
        assertThat(signal.basisDate()).isEqualTo(LocalDate.parse("2026-11-19"));
        assertThat(signal.probability()).isNull();
        verifyNoInteractions(kis, ai);
    }

    @Test
    void checksFridayOnWeekendAndEndsAtNextRegularClose() {
        LocalDate friday = LocalDate.parse("2026-11-20");
        stubValidInput("000660", friday, 0.48, 0.50);
        var signal = service("2026-11-22T11:00:00+09:00").analyze("000660", "KOSPI");
        assertThat(signal.decision()).isEqualTo("WAIT");
        assertThat(signal.basisDate()).isEqualTo(friday);
        assertThat(signal.expiresAt()).isEqualTo(OffsetDateTime.parse("2026-11-23T15:30:00+09:00"));
    }

    @Test
    void missingLatestOrIntermediateBarOnlyWithholdsThatStock() {
        LocalDate basis = LocalDate.parse("2026-11-18");
        List<LocalDate> dates = KrxDailySignalCalendar.window(basis);
        var request = new MarketDataRequest("005930", "KOSPI");
        var service = service("2026-11-18T20:15:00+09:00");
        when(kis.rawDailyCandles(request, dates.get(0), basis)).thenReturn(
            dates.subList(0, 20).stream().map(date -> candle(request, date, "1200")).toList(),
            dates.stream().filter(date -> !date.equals(dates.get(5))).map(date -> candle(request, date, "1200")).toList()
        );

        assertThat(service.analyze("005930", "KOSPI").holdReason()).isEqualTo("BAR_MISSING_OR_INVALID");
        assertThat(service.analyze("005930", "KOSPI").holdReason()).isEqualTo("BAR_MISSING_OR_INVALID");
        verifyNoInteractions(ai);
        stubValidInput("000660", basis, 0.60, 0.50);
        assertThat(service.analyze("000660", "KOSPI").decision()).isEqualTo("BUY_WATCH");
    }

    @Test
    void unmatchedReferenceCannotProduceProbability() {
        var request = new MarketDataRequest("005930", "KOSPI");
        LocalDate basis = LocalDate.parse("2026-11-19");
        var dates = KrxDailySignalCalendar.window(basis);
        when(kis.rawDailyCandles(request, dates.get(0), basis))
            .thenReturn(dates.stream().map(date -> candle(request, date, "1200")).toList());
        when(kis.rawDailyReference(request, basis)).thenReturn(Optional.of(candle(request, basis, "1100")));
        var signal = service("2026-11-19T20:16:00+09:00").analyze("005930", "KOSPI");
        assertThat(signal.holdReason()).isEqualTo("BAR_NOT_FINAL");
        verifyNoInteractions(ai);
    }

    @Test
    void missingCalendarOrUnsupportedMarketNeverReadsProvider() {
        var service = service("2026-12-30T21:00:00+09:00");
        assertThat(service.analyze("005930", "KOSPI").holdReason()).isEqualTo("CALENDAR_UNAVAILABLE");
        assertThat(service.analyze("005930", "KOSDAQ")).isNull();
        assertThat(service.analyze("035420", "KOSPI")).isNull();
        verifyNoInteractions(kis, ai);
    }

    @Test
    void nasdaqUsesNewYorkBasisAndExpiresAtEarlyClose() {
        LocalDate basis = LocalDate.parse("2026-11-25");
        var request = new MarketDataRequest("AAPL", "NASDAQ");
        var rows = NasdaqDailySignalCalendar.window(basis).stream()
            .map(day -> candle(request, day, "1200")).toList();
        assertThat(rows).hasSize(21);
        when(kis.usRawDailyCandles(request, basis)).thenReturn(rows);
        when(kis.usRawDailyCandles(request, null)).thenReturn(List.of(rows.get(20)));
        when(ai.inferDaily(any())).thenReturn(Optional.of(new DailyInference.Result("AAPL", basis,
            "us-daily-l2-logistic-v1", "a".repeat(64), 0.6, 0.6, Map.of(
                "openToClose", 0.1, "closeReturn1", 0.1, "closeReturn5", 0.1, "closeReturn20", 0.1,
                "rangeOverOpen", 0.1, "closeVolatility20", 0.1, "volumeRatio20", 0.1))));

        var signal = service("2026-11-26T10:20:00+09:00").analyze("AAPL", "NASDAQ");
        assertThat(signal.basisDate()).isEqualTo(basis);
        assertThat(signal.decision()).isEqualTo("BUY_WATCH");
        assertThat(signal.expiresAt()).isEqualTo(OffsetDateTime.parse("2026-11-27T13:00:00-05:00"));
        assertThat(signal.inputVersion()).isEqualTo("kis-nasdaq-raw-ohlcv-v1");
    }

    @Test
    void nasdaqWithholdsUntilNewYorkConfirmationAndAcrossSplit() {
        var duringConfirmation = service("2026-11-19T09:30:00+09:00").analyze("NVDA", "NASDAQ");
        assertThat(duringConfirmation.basisDate()).isEqualTo(LocalDate.parse("2026-11-18"));
        assertThat(duringConfirmation.holdReason()).isEqualTo("BAR_NOT_FINAL");
        verifyNoInteractions(kis, ai);
        LocalDate split = LocalDate.parse("2024-06-10");
        var request = new MarketDataRequest("NVDA", "NASDAQ");
        when(kis.usRawDailyCandles(request, split)).thenReturn(NasdaqDailySignalCalendar.window(split).stream()
            .map(day -> candle(request, day, "1200")).toList());
        var acrossSplit = service("2024-06-10T20:20:00-04:00").analyze("NVDA", "NASDAQ");
        assertThat(acrossSplit.holdReason()).isEqualTo("BAR_MISSING_OR_INVALID");
        verifyNoInteractions(ai);
    }

    private void stubValidInput(String code, LocalDate basisDate, double probability, double threshold) {
        List<LocalDate> dates = KrxDailySignalCalendar.window(basisDate);
        MarketDataRequest request = new MarketDataRequest(code, "KOSPI");
        when(kis.rawDailyCandles(request, dates.get(0), basisDate))
            .thenReturn(dates.stream().map(date -> candle(request, date, "1200")).toList());
        when(kis.rawDailyReference(request, basisDate)).thenReturn(Optional.of(candle(request, basisDate, "1200.0")));
        when(ai.inferDaily(any())).thenReturn(Optional.of(new DailyInference.Result(code, basisDate,
            "daily-l2-logistic-v1", "a".repeat(64), probability, threshold, Map.of(
                "openToClose", 0.1, "closeReturn1", 0.1, "closeReturn5", 0.1, "closeReturn20", 0.1,
                "rangeOverOpen", 0.1, "closeVolatility20", 0.1, "volumeRatio20", 0.1))));
    }

    private static StockCandle candle(MarketDataRequest request, LocalDate date, String volume) {
        return new StockCandle("KIS", request.stockCode(), request.market(), date.atStartOfDay(), CandleInterval.DAILY,
            new BigDecimal("100"), new BigDecimal("110"), new BigDecimal("90"), new BigDecimal("101"), new BigDecimal(volume));
    }

    private DailySignalService service(String now) {
        AiAnalysisProperties properties = new AiAnalysisProperties();
        properties.setEnabled(true);
        return new DailySignalService(kis, ai, properties,
            Clock.fixed(OffsetDateTime.parse(now).toInstant(), KrxDailySignalCalendar.SEOUL));
    }
}
