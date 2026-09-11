package com.sagopalgo.api.watchlist.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import com.sagopalgo.api.watchlist.dto.WatchlistAlertUpdateRequest;
import com.sagopalgo.api.watchlist.dto.WatchlistCreateRequest;
import com.sagopalgo.api.watchlist.dto.WatchlistCreateResponse;
import com.sagopalgo.api.watchlist.dto.WatchlistResponse;
import com.sagopalgo.api.watchlist.service.WatchlistService;
import jakarta.validation.Valid;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 관심 종목 API를 제공하는 컨트롤러입니다.
 */
@RestController
@RequestMapping("/api/v1/watchlist")
public class WatchlistController {

    private final WatchlistService watchlistService;

    public WatchlistController(WatchlistService watchlistService) {
        this.watchlistService = watchlistService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<WatchlistResponse>>> getWatchlist(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser
    ) {
        List<WatchlistResponse> response = watchlistService.findAll(authenticatedUser.userId());
        return ResponseEntity.ok(ApiResponse.success(response, "관심 종목 목록이 조회되었습니다."));
    }

    @PostMapping
    public ResponseEntity<ApiResponse<WatchlistCreateResponse>> createWatchlistItem(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @Valid @RequestBody WatchlistCreateRequest request
    ) {
        WatchlistCreateResponse response = watchlistService.create(authenticatedUser.userId(), request);
        return ResponseEntity.ok(ApiResponse.success(response, "관심 종목이 추가되었습니다."));
    }

    @PatchMapping("/{watchlistId}/alert")
    public ResponseEntity<ApiResponse<WatchlistResponse>> updateAlert(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @PathVariable Long watchlistId,
        @Valid @RequestBody WatchlistAlertUpdateRequest request
    ) {
        WatchlistResponse response = watchlistService.updateAlert(authenticatedUser.userId(), watchlistId, request);
        return ResponseEntity.ok(ApiResponse.success(response, "관심 종목 알림 설정이 변경되었습니다."));
    }

    @DeleteMapping("/{watchlistId}")
    public ResponseEntity<ApiResponse<Void>> deleteWatchlistItem(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @PathVariable Long watchlistId
    ) {
        watchlistService.delete(authenticatedUser.userId(), watchlistId);
        return ResponseEntity.ok(ApiResponse.success(null, "관심 종목이 삭제되었습니다."));
    }
}
