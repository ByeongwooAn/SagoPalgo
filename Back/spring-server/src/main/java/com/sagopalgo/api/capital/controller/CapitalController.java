package com.sagopalgo.api.capital.controller;

import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.dto.UpdateCapitalRequest;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.security.JwtAuthenticatedUser;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * 사용자 자본금 API를 제공하는 컨트롤러입니다.
 */
@RestController
@RequestMapping("/api/v1/capital")
public class CapitalController {

    private final CapitalService capitalService;

    public CapitalController(CapitalService capitalService) {
        this.capitalService = capitalService;
    }

    @GetMapping
    public ResponseEntity<ApiResponse<CapitalResponse>> getCapital(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser
    ) {
        CapitalResponse response = capitalService.findByUserId(authenticatedUser.userId());
        return ResponseEntity.ok(ApiResponse.success(response, "자본금이 조회되었습니다."));
    }

    @PutMapping
    public ResponseEntity<ApiResponse<CapitalResponse>> updateCapital(
        @AuthenticationPrincipal JwtAuthenticatedUser authenticatedUser,
        @Valid @RequestBody UpdateCapitalRequest request
    ) {
        CapitalResponse response = capitalService.update(authenticatedUser.userId(), request);
        return ResponseEntity.ok(ApiResponse.success(response, "자본금이 수정되었습니다."));
    }
}
