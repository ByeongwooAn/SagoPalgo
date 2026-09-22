package com.sagopalgo.api.papertrading.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.papertrading.dto.PaperBuyRequest;
import com.sagopalgo.api.papertrading.dto.PaperSellRequest;
import com.sagopalgo.api.papertrading.dto.PaperTradingSnapshotResponse;
import com.sagopalgo.api.papertrading.service.PaperTradingService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 실제 증권사 주문과 분리된 AI 신호 기반 모의매매 API입니다.
 */
@RestController
@RequestMapping("/api/v1/paper-trading")
public class PaperTradingController {

    private final PaperTradingService paperTradingService;
    private final LocalUserContext localUserContext;

    public PaperTradingController(
        PaperTradingService paperTradingService,
        LocalUserContext localUserContext
    ) {
        this.paperTradingService = paperTradingService;
        this.localUserContext = localUserContext;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<PaperTradingSnapshotResponse>> getSnapshot() {
        return ResponseEntity.ok(ApiResponse.success(
            paperTradingService.getSnapshot(localUserContext.userId()),
            "모의매매 현황이 조회되었습니다."
        ));
    }

    @PostMapping("/recommendations/{recommendationId}/buy")
    public ResponseEntity<ApiResponse<PaperTradingSnapshotResponse>> buy(
        @PathVariable Long recommendationId,
        @Valid @RequestBody PaperBuyRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            paperTradingService.buyFromRecommendation(
                localUserContext.userId(),
                recommendationId,
                request
            ),
            "AI 신호 모의매수가 체결되었습니다."
        ));
    }

    @PostMapping("/sell")
    public ResponseEntity<ApiResponse<PaperTradingSnapshotResponse>> sell(
        @Valid @RequestBody PaperSellRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            paperTradingService.sell(localUserContext.userId(), request),
            "모의매도가 체결되었습니다."
        ));
    }
}
