package com.sagopalgo.api.kb.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.kb.dto.AccountObservationCollectionResponse;
import com.sagopalgo.api.kb.service.AccountObservationCollectionService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/kb/accounts/primary/observations/collection")
public class AccountObservationCollectionController {
    private final AccountObservationCollectionService service;
    private final LocalUserContext user;
    public AccountObservationCollectionController(AccountObservationCollectionService service,LocalUserContext user) {
        this.service=service;this.user=user;
    }
    public record ResumeRequest(@NotBlank String lastRequestId) {}

    @GetMapping
    public ResponseEntity<ApiResponse<AccountObservationCollectionResponse>> status() {
        return response(service.status(user.userId()));
    }
    @PostMapping("/resume")
    public ResponseEntity<ApiResponse<AccountObservationCollectionResponse>> resume(@Valid @RequestBody ResumeRequest request) {
        return response(service.resume(user.userId(),request.lastRequestId()));
    }
    private ResponseEntity<ApiResponse<AccountObservationCollectionResponse>> response(AccountObservationCollectionResponse value) {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(value,
            "계좌 읽기 관찰의 수집 상태입니다. 자동 주문·원장 반영을 수행하지 않습니다."));
    }
}
