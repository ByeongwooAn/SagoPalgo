package com.sagopalgo.api.dashboard.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.dashboard.dto.DashboardSnapshotResponse;
import com.sagopalgo.api.dashboard.service.DashboardService;
import com.sagopalgo.api.user.service.LocalUserContext;
import org.springframework.http.ResponseEntity;
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
    private final LocalUserContext localUserContext;

    public DashboardController(DashboardService dashboardService, LocalUserContext localUserContext) {
        this.dashboardService = dashboardService;
        this.localUserContext = localUserContext;
    }

    @GetMapping("/snapshot")
    public ResponseEntity<ApiResponse<DashboardSnapshotResponse>> getSnapshot() {
        DashboardSnapshotResponse response = dashboardService.getSnapshot(localUserContext.userId());
        return ResponseEntity.ok(ApiResponse.success(response, "대시보드 데이터가 조회되었습니다."));
    }
}
