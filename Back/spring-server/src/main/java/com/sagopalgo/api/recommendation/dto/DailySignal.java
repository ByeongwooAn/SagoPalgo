package com.sagopalgo.api.recommendation.dto;

import com.fasterxml.jackson.annotation.JsonFormat;
import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record DailySignal(
    String decision,
    String holdReason,
    String modelVersion,
    String modelSha256,
    String inputVersion,
    @JsonFormat(shape = JsonFormat.Shape.STRING) LocalDate basisDate,
    @JsonFormat(shape = JsonFormat.Shape.STRING) LocalDate inputStartDate,
    @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime evaluatedAt,
    @JsonFormat(shape = JsonFormat.Shape.STRING) OffsetDateTime expiresAt,
    Double probability,
    Double threshold,
    Map<String, Double> contributions
) {
    public static DailySignal withheld(String reason, LocalDate basisDate, OffsetDateTime evaluatedAt) {
        return new DailySignal("WITHHELD", reason, null, null, null, basisDate, null, evaluatedAt, null, null, null, null);
    }
}
