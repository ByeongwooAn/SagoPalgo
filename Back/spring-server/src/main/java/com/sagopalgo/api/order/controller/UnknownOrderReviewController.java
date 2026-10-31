package com.sagopalgo.api.order.controller;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.service.UnknownOrderReviewService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/orders/manual/{id}/reviews")
public class UnknownOrderReviewController {
    private final UnknownOrderReviewService service;private final LocalUserContext user;
    public UnknownOrderReviewController(UnknownOrderReviewService service,LocalUserContext user){this.service=service;this.user=user;}
    @GetMapping public ApiResponse<List<UnknownOrderReviewService.Response>> history(@PathVariable String id){return ApiResponse.success(service.history(user.userId(),id),"저장된 대조 관찰. KB 호출 없음");}
    @PostMapping("/prepare") public ApiResponse<UnknownOrderReviewService.Preparation> prepare(@PathVariable String id,@Valid @RequestBody Prepare r){return ApiResponse.success(service.prepare(user.userId(),id,r.orderNo()),"읽기 전용 대조 준비. 차단 유지");}
    @PostMapping("/confirm") public ApiResponse<UnknownOrderReviewService.Response> confirm(@PathVariable String id,@Valid @RequestBody Confirm r){return ApiResponse.success(service.confirm(user.userId(),id,r.reviewId(),r.token(),r.acknowledged(),r.confirmation()),"대조 관찰 저장. 차단 유지");}
    public record Prepare(@NotBlank @Pattern(regexp="[0-9]{10}") String orderNo){}
    public record Confirm(@NotBlank @Size(max=36) String reviewId,@NotBlank @Size(max=200) String token,boolean acknowledged,@NotBlank String confirmation){}
}
