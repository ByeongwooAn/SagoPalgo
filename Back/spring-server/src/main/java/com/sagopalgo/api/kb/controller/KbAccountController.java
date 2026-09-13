package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.KbAccountListResponse;
import com.sagopalgo.api.kb.dto.KbBalanceResponse;
import com.sagopalgo.api.kb.dto.KbHoldingsResponse;
import com.sagopalgo.api.kb.service.KbAccountService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * KB증권 계좌/보유 주식 조회 API입니다.
 */
@RestController
@RequestMapping("/api/v1/kb")
public class KbAccountController {

    private final KbAccountService kbAccountService;

    public KbAccountController(KbAccountService kbAccountService) {
        this.kbAccountService = kbAccountService;
    }

    @GetMapping("/accounts")
    public ResponseEntity<ApiResponse<KbAccountListResponse>> accounts() {
        return ResponseEntity.ok(ApiResponse.success(kbAccountService.accounts(), "KB증권 계좌 목록이 조회되었습니다."));
    }

    @GetMapping("/accounts/primary/holdings")
    public ResponseEntity<ApiResponse<KbHoldingsResponse>> holdings() {
        return ResponseEntity.ok(ApiResponse.success(kbAccountService.holdings(), "KB증권 보유 주식이 조회되었습니다."));
    }

    @GetMapping("/accounts/primary/balances/settlement")
    public ResponseEntity<ApiResponse<KbBalanceResponse>> settlementBalance() {
        return ResponseEntity.ok(ApiResponse.success(kbAccountService.settlementBalance(), "KB증권 결제기준 잔고 현황이 조회되었습니다."));
    }

    @GetMapping("/accounts/primary/balances/execution")
    public ResponseEntity<ApiResponse<KbBalanceResponse>> executionBalance() {
        return ResponseEntity.ok(ApiResponse.success(kbAccountService.executionBalance(), "KB증권 체결기준 잔고 현황이 조회되었습니다."));
    }
}
