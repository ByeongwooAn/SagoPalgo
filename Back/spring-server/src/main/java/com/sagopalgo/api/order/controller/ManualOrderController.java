package com.sagopalgo.api.order.controller;

import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.dto.*;
import com.sagopalgo.api.order.service.ManualOrderService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.math.BigDecimal;
import java.util.List;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/orders/manual")
public class ManualOrderController {
    private final ManualOrderService service;
    private final LocalUserContext user;
    public ManualOrderController(ManualOrderService service,LocalUserContext user){this.service=service;this.user=user;}
    @GetMapping public ApiResponse<List<ManualOrderResponse>> history(){return ApiResponse.success(service.history(user.userId()),"수동 주문 기록");}
    @GetMapping("/{id}") public ApiResponse<ManualOrderResponse> get(@PathVariable String id){return ApiResponse.success(service.get(user.userId(),id),"주문 기록");}
    @PostMapping public ApiResponse<ManualOrderResponse> submit(@Valid @RequestBody Submit request){
        return ApiResponse.success(service.submit(user.userId(),request.approvalId(),request.acknowledged(),request.confirmation()),"수동 전송 결과");
    }
    @PostMapping("/{id}/observations") public ApiResponse<ManualOrderObservation> sync(@PathVariable String id){
        return ApiResponse.success(service.sync(user.userId(),id),"KB 체결 조회 결과");
    }
    @GetMapping("/{id}/observations") public ApiResponse<List<ManualOrderObservation>> observations(@PathVariable String id){
        return ApiResponse.success(service.observations(user.userId(),id),"체결 조회 이력");
    }
    @PostMapping("/{id}/changes/prepare") public ApiResponse<ManualOrderService.ChangePreparation> prepare(
        @PathVariable String id,@Valid @RequestBody Change request){
        return ApiResponse.success(service.prepareChange(user.userId(),id,request.kind(),request.price(),request.quantity(),request.reuseReservation()),"정정·취소 준비");
    }
    @PostMapping("/{id}/submit") public ApiResponse<ManualOrderResponse> change(@PathVariable String id,@Valid @RequestBody Confirm request){
        return ApiResponse.success(service.submitChange(user.userId(),id,request.token(),request.acknowledged(),request.confirmation()),"수동 전송 결과");
    }
    public record Submit(@NotNull @Positive Long approvalId,boolean acknowledged,@NotBlank String confirmation){}
    public record Change(@NotBlank @Pattern(regexp="AMEND|CANCEL") String kind,@Digits(integer=9,fraction=0) BigDecimal price,
        @Positive @Digits(integer=10,fraction=0) BigDecimal quantity,boolean reuseReservation){}
    public record Confirm(@NotBlank @Size(max=200) String token,boolean acknowledged,@NotBlank String confirmation){}
}
