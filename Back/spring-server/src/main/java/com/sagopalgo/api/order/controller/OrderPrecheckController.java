package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckHistoryResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderPrecheckResponse;
import com.sagopalgo.api.order.service.OrderPrecheckService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

/**
 * 실제 주문을 보내지 않는 주문 사전검증 API입니다.
 */
@Validated
@RestController
@RequestMapping("/api/v1/orders")
public class OrderPrecheckController {

    private final OrderPrecheckService service;
    private final LocalUserContext localUserContext;

    public OrderPrecheckController(OrderPrecheckService service, LocalUserContext localUserContext) {
        this.service = service;
        this.localUserContext = localUserContext;
    }

    @PostMapping("/precheck")
    public ResponseEntity<ApiResponse<OrderPrecheckResponse>> precheck(
        @Valid @RequestBody OrderPrecheckRequest request
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.precheck(localUserContext.userId(), request),
            "주문 사전검증이 완료되었습니다. 실제 주문은 전송되지 않았습니다."
        ));
    }

    @GetMapping("/prechecks")
    public ResponseEntity<ApiResponse<OrderPrecheckHistoryResponse>> history(
        @RequestParam(defaultValue = "20") @Min(1) @Max(100) int limit
    ) {
        return ResponseEntity.ok(ApiResponse.success(
            service.history(localUserContext.userId(), limit),
            "주문 사전검증 이력이 조회되었습니다."
        ));
    }
}
