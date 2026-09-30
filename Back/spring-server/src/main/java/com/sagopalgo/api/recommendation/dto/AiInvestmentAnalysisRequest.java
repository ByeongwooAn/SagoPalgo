package com.sagopalgo.api.recommendation.dto;

import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.List;

/**
 * Spring이 Python 분석 서버에 전달하는 종목 분석 입력입니다.
 */
public record AiInvestmentAnalysisRequest(
    String stockCode,
    String stockName,
    String market,
    BigDecimal currentPrice,
    BigDecimal buyPrice,
    BigDecimal profitRate,
    BigDecimal stopLossRate,
    BigDecimal takeProfitRate,
    List<CandleInput> candles,
    List<NewsInput> news,
    List<DisclosureInput> disclosures,
    String analysisType
) {
    public record CandleInput(
        LocalDateTime dateTime,
        BigDecimal closePrice,
        BigDecimal volume
    ) {
    }

    public record NewsInput(String title, String summary) {
    }

    public record DisclosureInput(String reportName) {
    }
}
