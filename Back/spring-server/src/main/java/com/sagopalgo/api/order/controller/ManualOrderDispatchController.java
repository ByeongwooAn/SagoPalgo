package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.service.ManualOrderDispatchService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/orders/manual/{id}/dispatch")
public class ManualOrderDispatchController {
    private final ManualOrderDispatchService service;
    private final LocalUserContext user;
    public ManualOrderDispatchController(ManualOrderDispatchService service, LocalUserContext user) {
        this.service=service; this.user=user;
    }
    @GetMapping public ApiResponse<ManualOrderDispatchService.Status> status(@PathVariable String id) {
        return ApiResponse.success(service.status(user.userId(),id),"전송 기록 조회. KB 호출 없음");
    }
    @PostMapping("/recover") public ApiResponse<ManualOrderDispatchService.Status> recover(
        @PathVariable String id,@Valid @RequestBody Confirm request) {
        service.recover(user.userId(),id,request.acknowledged(),request.confirmation());
        return ApiResponse.success(service.status(user.userId(),id),"저장 결과 복구. 추가 주문 전송 없음");
    }
    public record Confirm(boolean acknowledged,@NotBlank String confirmation){}
}
