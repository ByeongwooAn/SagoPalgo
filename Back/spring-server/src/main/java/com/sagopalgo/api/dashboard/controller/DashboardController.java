package com.sagopalgo.api.dashboard.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.dashboard.dto.DashboardSnapshotResponse;
import com.sagopalgo.api.dashboard.service.DashboardService;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 앱 초기 진입에 필요한 투자 스냅샷 API를 제공하는 컨트롤러입니다.
 */
@RestController
@RequestMapping("/api/v1/dashboard")
public class DashboardController {

    private final DashboardService dashboardService;

    public DashboardController(DashboardService dashboardService) {
        this.dashboardService = dashboardService;
    }

    @GetMapping("/snapshot")
    public ResponseEntity<ApiResponse<DashboardSnapshotResponse>> getSnapshot(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser
    ) {
        DashboardSnapshotResponse response = dashboardService.getSnapshot(authenticatedUser.userId());
        return ResponseEntity.ok(ApiResponse.success(response, "대시보드 데이터가 조회되었습니다."));
    }
}
