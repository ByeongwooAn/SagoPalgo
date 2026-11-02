package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse;
import com.sagopalgo.api.kb.service.AccountObservationComparisonService;
import com.sagopalgo.api.user.service.LocalUserContext;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/kb/accounts/primary/observations")
public class AccountObservationComparisonController {
    private final AccountObservationComparisonService service;
    private final LocalUserContext user;

    public AccountObservationComparisonController(AccountObservationComparisonService service, LocalUserContext user) {
        this.service = service;
        this.user = user;
    }

    @GetMapping("/comparison")
    public ResponseEntity<ApiResponse<AccountObservationComparisonResponse>> compare(
        @RequestParam(defaultValue="") String beforeRequestId, @RequestParam(defaultValue="") String afterRequestId
    ) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
            service.compare(user.userId(),beforeRequestId,afterRequestId),
            "저장된 관찰의 필드 차이입니다. 거래·입출금·주문 종결을 판정하지 않습니다."));
    }
}
