package com.sagopalgo.api.holding.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.holding.dto.HoldingCreateResponse;
import com.sagopalgo.api.holding.dto.HoldingRequest;
import com.sagopalgo.api.holding.dto.HoldingResponse;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 보유 종목 API를 제공하는 컨트롤러입니다.
 */
@RestController
@RequestMapping("/api/v1/holdings")
public class HoldingController {

    private final HoldingService holdingService;

    public HoldingController(HoldingService holdingService) {
        this.holdingService = holdingService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<HoldingsListResponse>> getHoldings(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser
    ) {
        HoldingsListResponse response = holdingService.findAll(authenticatedUser.userId());
        return ResponseEntity.ok(ApiResponse.success(response, "보유 종목이 조회되었습니다."));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<HoldingCreateResponse>> createHolding(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @Valid @RequestBody HoldingRequest request
    ) {
        HoldingCreateResponse response = holdingService.create(authenticatedUser.userId(), request);
        return ResponseEntity.ok(ApiResponse.success(response, "보유 종목이 등록되었습니다."));
    }

    @PutMapping("/{holdingId}")
    public ResponseEntity<ApiResponse<HoldingResponse>> updateHolding(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @PathVariable Long holdingId,
        @Valid @RequestBody HoldingRequest request
    ) {
        HoldingResponse response = holdingService.update(authenticatedUser.userId(), holdingId, request);
        return ResponseEntity.ok(ApiResponse.success(response, "보유 종목이 수정되었습니다."));
    }

    @DeleteMapping("/{holdingId}")
    public ResponseEntity<ApiResponse<Void>> deleteHolding(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @PathVariable Long holdingId
    ) {
        holdingService.delete(authenticatedUser.userId(), holdingId);
        return ResponseEntity.ok(ApiResponse.success(null, "보유 종목이 삭제되었습니다."));
    }
}
