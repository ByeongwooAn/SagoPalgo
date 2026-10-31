package com.sagopalgo.api.order.simulation;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.List;
import java.util.Map;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/orders/simulations")
public class OrderSimulationController {
    private final OrderSimulationService service;
    private final LocalUserContext user;
    public OrderSimulationController(OrderSimulationService service, LocalUserContext user) { this.service=service; this.user=user; }
    @GetMapping public ApiResponse<List<Map<String,Object>>> sessions() { return ApiResponse.success(service.sessions(user.userId()), "SIMULATION 세션 목록"); }
    @PostMapping public ApiResponse<Map<String,Object>> create(@Valid @RequestBody Create request) {
        return ok(service.create(user.userId(), request.cash()));
    }
    @GetMapping("/{id}") public ApiResponse<Map<String,Object>> get(@PathVariable String id) { return ok(service.get(user.userId(),id)); }
    @PostMapping("/{id}/quotes") public ApiResponse<Map<String,Object>> quote(@PathVariable String id,@Valid @RequestBody Quote request) {
        return ok(service.quote(user.userId(),id,request.market(),request.stockCode(),request.price()));
    }
    @PostMapping("/{id}/commands/prepare") public ApiResponse<Map<String,Object>> prepare(@PathVariable String id,@Valid @RequestBody Prepare request) {
        return ok(service.prepare(user.userId(),id,request.plan(),request.kind(),request.parentId(),request.scenario()));
    }
    @PostMapping("/{id}/commands/{commandId}/confirm") public ApiResponse<Map<String,Object>> confirm(
        @PathVariable String id,@PathVariable String commandId,@Valid @RequestBody Confirm request) {
        return ok(service.confirm(user.userId(),id,commandId,request.token(),request.acknowledged()));
    }
    @PostMapping("/{id}/commands/{commandId}/submit") public ApiResponse<Map<String,Object>> submit(
        @PathVariable String id,@PathVariable String commandId,@Valid @RequestBody Submit request) {
        return ok(service.submit(user.userId(),id,commandId,request.acknowledged(),request.confirmation()));
    }
    @PostMapping("/{id}/orders/{orderNo}/fill") public ApiResponse<Map<String,Object>> fill(
        @PathVariable String id,@PathVariable String orderNo,@Valid @RequestBody Fill request) {
        return ok(service.fill(user.userId(),id,orderNo,request.quantity()));
    }
    private ApiResponse<Map<String,Object>> ok(Map<String,Object> data) { return ApiResponse.success(data,"SIMULATION 전용 결과. 실제 주문 전송 없음"); }
    public record Create(@NotNull @DecimalMin("0.01") @Digits(integer=10,fraction=2) BigDecimal cash) {}
    public record Quote(@NotBlank String stockCode,@NotBlank String market,@NotNull BigDecimal price) {}
    public record Prepare(@NotNull @Valid OrderPrecheckRequest plan,@NotBlank String kind,String parentId,@NotBlank String scenario) {}
    public record Confirm(@NotBlank @Size(max=200) String token,boolean acknowledged) {}
    public record Submit(boolean acknowledged,@NotBlank String confirmation) {}
    public record Fill(@NotNull @DecimalMin("1") @Digits(integer=10,fraction=4) BigDecimal quantity) {}
}
