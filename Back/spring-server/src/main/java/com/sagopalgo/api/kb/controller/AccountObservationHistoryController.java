package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.service.AccountObservationHistoryService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/kb/accounts/primary/observations")
public class AccountObservationHistoryController {
    private final AccountObservationHistoryService service;
    private final LocalUserContext user;

    public AccountObservationHistoryController(AccountObservationHistoryService service, LocalUserContext user) {
        this.service = service;
        this.user = user;
    }

    public record CaptureRequest(@NotBlank String requestId, @NotBlank String orderDate) {}

    @PostMapping
    public ResponseEntity<ApiResponse<AccountObservationResponse>> capture(@Valid @RequestBody CaptureRequest request) {
        return response(service.capture(user.userId(), request.requestId(), request.orderDate()), "계좌 관찰 저장 요청 결과입니다.");
    }

    @GetMapping
    public ResponseEntity<ApiResponse<AccountObservationResponse.Page>> history(
        @RequestParam(required=false) Long beforeId, @RequestParam(defaultValue="20") int limit
    ) {
        return response(service.history(user.userId(), beforeId, limit), "현재 계좌 연결의 관찰 이력입니다.");
    }

    @GetMapping("/{requestId}")
    public ResponseEntity<ApiResponse<AccountObservationResponse>> detail(@PathVariable String requestId) {
        return response(service.detail(user.userId(), requestId), "저장된 계좌 관찰입니다. KB를 다시 조회하지 않습니다.");
    }

    private <T> ResponseEntity<ApiResponse<T>> response(T data, String message) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(data, message));
    }
}
