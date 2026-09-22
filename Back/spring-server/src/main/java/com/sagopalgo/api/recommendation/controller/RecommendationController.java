package com.sagopalgo.api.recommendation.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationListResponse;
import com.sagopalgo.api.recommendation.dto.RecommendationResponse;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import com.sagopalgo.api.user.service.LocalUserContext;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 보유 종목 분석 실행과 저장 추천 이력 조회 API입니다.
 */
@RestController
@RequestMapping("/api/v1/recommendations")
public class RecommendationController {

    private final RecommendationService recommendationService;
    private final LocalUserContext localUserContext;

    public RecommendationController(
        RecommendationService recommendationService,
        LocalUserContext localUserContext
    ) {
        this.recommendationService = recommendationService;
        this.localUserContext = localUserContext;
    }

    @PostMapping("/analyze/{holdingId}")
    public ResponseEntity<ApiResponse<RecommendationResponse>> analyze(
        @PathVariable Long holdingId
    ) {
        RecommendationResponse response = recommendationService.analyzeHolding(
            localUserContext.userId(),
            holdingId
        );
        return ResponseEntity.ok(ApiResponse.success(response, "종목 분석과 추천 저장이 완료되었습니다."));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<RecommendationListResponse>> findAll(
        @RequestParam(required = false) String status,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        RecommendationListResponse response = recommendationService.findAll(
            localUserContext.userId(),
            status,
            page,
            size
        );
        return ResponseEntity.ok(ApiResponse.success(response, "추천 이력이 조회되었습니다."));
    }

    @GetMapping("/{recommendationId}")
    public ResponseEntity<ApiResponse<RecommendationResponse>> findOne(
        @PathVariable Long recommendationId
    ) {
        RecommendationResponse response = recommendationService.findOne(
            localUserContext.userId(),
            recommendationId
        );
        return ResponseEntity.ok(ApiResponse.success(response, "추천 상세가 조회되었습니다."));
    }
}
