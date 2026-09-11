package com.sagopalgo.api.settings.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.settings.dto.ProviderSettingsResponse;
import com.sagopalgo.api.settings.service.ProviderSettingsService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 개인용 프로그램의 외부 증권사 연동 상태를 조회하는 API입니다.
 */
@RestController
@RequestMapping("/api/v1/settings/providers")
public class ProviderSettingsController {

    private final ProviderSettingsService providerSettingsService;

    public ProviderSettingsController(ProviderSettingsService providerSettingsService) {
        this.providerSettingsService = providerSettingsService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<ProviderSettingsResponse>> getProviderSettings() {
        ProviderSettingsResponse response = providerSettingsService.getSettings();
        return ResponseEntity.ok(ApiResponse.success(response, "증권사 연동 설정이 조회되었습니다."));
    }
}
