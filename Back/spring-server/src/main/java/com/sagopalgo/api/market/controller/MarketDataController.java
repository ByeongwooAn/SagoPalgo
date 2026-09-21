package com.sagopalgo.api.market.controller;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.market.dto.MarketCandleResponse;
import com.sagopalgo.api.market.model.CandleInterval;
import com.sagopalgo.api.market.service.MarketCandleService;
import java.util.Locale;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 외부 증권사 데이터를 내부 표준 시장 데이터 형태로 제공합니다.
 */
@RestController
@RequestMapping("/api/v1/market")
public class MarketDataController {

    private final MarketCandleService marketCandleService;

    public MarketDataController(MarketCandleService marketCandleService) {
        this.marketCandleService = marketCandleService;
    }

    @GetMapping("/candles")
    public ResponseEntity<ApiResponse<MarketCandleResponse>> getCandles(
        @RequestParam String stockCode,
        @RequestParam(defaultValue = "KOSPI") String market,
        @RequestParam(defaultValue = "DAILY") String interval,
        @RequestParam(defaultValue = "60") String count
    ) {
        MarketCandleResponse response = marketCandleService.getCandles(
            stockCode,
            market,
            parseInterval(interval),
            parseCount(count)
        );
        return ResponseEntity.ok(ApiResponse.success(response, "종목 캔들 시세가 조회되었습니다."));
    }

    private CandleInterval parseInterval(String value) {
        try {
            return CandleInterval.valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 주기는 DAILY, WEEKLY, MONTHLY 중 하나여야 합니다.");
        }
    }

    private int parseCount(String value) {
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException | NullPointerException exception) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "캔들 조회 건수는 1~100 사이의 숫자여야 합니다.");
        }
    }
}
