package com.sagopalgo.api.alert.controller;

import com.sagopalgo.api.alert.dto.AlertListResponse;
import com.sagopalgo.api.alert.dto.AlertResponse;
import com.sagopalgo.api.alert.service.AlertService;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.user.service.LocalUserContext;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 앱 알림 이력과 Windows 로컬 알림 전달 상태 API입니다.
 */
@RestController
@RequestMapping("/api/v1/alerts")
public class AlertController {

    private final AlertService alertService;
    private final LocalUserContext localUserContext;

    public AlertController(AlertService alertService, LocalUserContext localUserContext) {
        this.alertService = alertService;
        this.localUserContext = localUserContext;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<AlertListResponse>> findAll(
        @RequestParam(defaultValue = "false") boolean unreadOnly,
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size
    ) {
        AlertListResponse response = alertService.findAll(
            localUserContext.userId(),
            unreadOnly,
            page,
            size
        );
        return ResponseEntity.ok(ApiResponse.success(response, "알림 이력이 조회되었습니다."));
    }

    @GetMapping("/pending")
    public ResponseEntity<ApiResponse<List<AlertResponse>>> findPending(
        @RequestParam(defaultValue = "20") int limit
    ) {
        List<AlertResponse> response = alertService.findPending(localUserContext.userId(), limit);
        return ResponseEntity.ok(ApiResponse.success(response, "전달 대기 알림이 조회되었습니다."));
    }

    @PatchMapping("/{alertId}/sent")
    public ResponseEntity<ApiResponse<AlertResponse>> markSent(@PathVariable Long alertId) {
        AlertResponse response = alertService.markSent(localUserContext.userId(), alertId);
        return ResponseEntity.ok(ApiResponse.success(response, "Windows 알림 전달이 기록되었습니다."));
    }

    @PatchMapping("/{alertId}/read")
    public ResponseEntity<ApiResponse<AlertResponse>> markRead(@PathVariable Long alertId) {
        AlertResponse response = alertService.markRead(localUserContext.userId(), alertId);
        return ResponseEntity.ok(ApiResponse.success(response, "알림을 읽음 처리했습니다."));
    }
}
