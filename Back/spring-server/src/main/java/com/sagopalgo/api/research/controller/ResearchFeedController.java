package com.sagopalgo.api.research.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.service.ResearchFeedService;
import java.time.LocalDate;
import org.springframework.format.annotation.DateTimeFormat;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 종목별 뉴스와 공시를 동기화하고 로컬 저장 결과를 조회하는 API입니다.
 */
@RestController
@RequestMapping("/api/v1/research")
public class ResearchFeedController {

    private final ResearchFeedService researchFeedService;

    public ResearchFeedController(ResearchFeedService researchFeedService) {
        this.researchFeedService = researchFeedService;
    }

    @GetMapping("/feed")
    public ResponseEntity<ApiResponse<ResearchFeedResponse>> getFeed(
        @RequestParam String stockCode,
        @RequestParam String stockName,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate fromDate,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate toDate
    ) {
        ResearchFeedResponse response = researchFeedService.getStoredFeed(stockCode, stockName, fromDate, toDate);
        return ResponseEntity.ok(ApiResponse.success(response, "저장된 종목 뉴스와 공시가 조회되었습니다."));
    }

    @PostMapping("/feed/sync")
    public ResponseEntity<ApiResponse<ResearchFeedResponse>> syncFeed(
        @RequestParam String stockCode,
        @RequestParam String stockName,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate fromDate,
        @RequestParam(required = false) @DateTimeFormat(iso = DateTimeFormat.ISO.DATE) LocalDate toDate
    ) {
        ResearchFeedResponse response = researchFeedService.syncFeed(stockCode, stockName, fromDate, toDate);
        return ResponseEntity.ok(ApiResponse.success(response, "종목 뉴스와 공시가 동기화되었습니다."));
    }
}
