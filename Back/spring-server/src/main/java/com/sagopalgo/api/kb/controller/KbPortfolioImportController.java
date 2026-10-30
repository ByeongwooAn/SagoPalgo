package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioImportRequest;
import com.sagopalgo.api.kb.dto.KbPortfolioImportResponse;
import com.sagopalgo.api.kb.dto.KbPortfolioPreviewResponse;
import com.sagopalgo.api.kb.service.KbPortfolioImportService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/kb/portfolio-import")
public class KbPortfolioImportController {
    private final KbPortfolioImportService service;
    private final LocalUserContext user;

    public KbPortfolioImportController(KbPortfolioImportService service, LocalUserContext user) {
        this.service = service;
        this.user = user;
    }

    @GetMapping("/preview")
    public ApiResponse<KbPortfolioPreviewResponse> preview() {
        return ApiResponse.success(service.preview(user.userId()), "KB 반영 미리보기입니다. 아직 앱 데이터는 변경하지 않았습니다.");
    }

    @PostMapping
    public ApiResponse<KbPortfolioImportResponse> apply(@Valid @RequestBody KbPortfolioImportRequest request) {
        return ApiResponse.success(service.apply(user.userId(), request), "선택한 KB 데이터를 앱에 반영했습니다.");
    }
}
