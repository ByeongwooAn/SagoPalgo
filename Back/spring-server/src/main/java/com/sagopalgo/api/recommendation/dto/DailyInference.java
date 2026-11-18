package com.sagopalgo.api.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

public final class DailyInference {
    private DailyInference() {}

    public record Request(
        String stockCode, String market, String provider, String priceBasis,
        @JsonFormat(shape = JsonFormat.Shape.STRING) LocalDate signalDate, List<Bar> bars
    ) {}

    public record Bar(
        @JsonFormat(shape = JsonFormat.Shape.STRING) LocalDate businessDate,
        BigDecimal opened, BigDecimal high, BigDecimal low, BigDecimal closed, BigDecimal volume
    ) {}

    public record Result(
        String stockCode, LocalDate signalDate, String modelVersion, String modelSha256,
        Double probability, Double threshold, Map<String, Double> contributions
    ) {}
}
