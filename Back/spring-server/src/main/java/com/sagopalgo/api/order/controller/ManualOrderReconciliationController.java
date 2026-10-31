package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.ManualOrderReconciliationResponse;
import com.sagopalgo.api.order.service.ManualOrderReconciliationService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/orders/manual/{id}/reconciliation")
public class ManualOrderReconciliationController {
    private final ManualOrderReconciliationService service;
    private final LocalUserContext user;

    public ManualOrderReconciliationController(ManualOrderReconciliationService service, LocalUserContext user) {
        this.service = service;
        this.user = user;
    }

    @PostMapping("/prepare")
    public ApiResponse<ManualOrderReconciliationService.Preparation> prepare(@PathVariable String id,
        @Valid @RequestBody Prepare request) {
        return ApiResponse.success(service.prepare(user.userId(), id, request.orderNo()), "읽기 전용 체결 대조 결과");
    }

    @PostMapping("/confirm")
    public ApiResponse<ManualOrderReconciliationResponse> confirm(@PathVariable String id,
        @Valid @RequestBody Confirm request) {
        return ApiResponse.success(service.confirm(user.userId(), id, request.token(), request.acknowledged(),
            request.confirmation()), "전량 체결 대조 확정. 실제 주문을 전송하지 않았습니다.");
    }

    public record Prepare(@NotBlank @Pattern(regexp = "[0-9]{10}") String orderNo) {}
    public record Confirm(@NotBlank @Size(max = 200) String token, boolean acknowledged, @NotBlank String confirmation) {}
}
