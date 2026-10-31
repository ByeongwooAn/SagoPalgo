package com.sagopalgo.api.order.controller;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.order.service.ManualOrderDiagnosticService;
import com.sagopalgo.api.user.service.LocalUserContext;
import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.util.List;
import org.springframework.web.bind.annotation.*;
@RestController
@RequestMapping("/api/v1/orders/manual/{id}/diagnostics")
public class ManualOrderDiagnosticController {
    private final ManualOrderDiagnosticService service;
    private final LocalUserContext user;
    public ManualOrderDiagnosticController(ManualOrderDiagnosticService service,LocalUserContext user){this.service=service;this.user=user;}
    @GetMapping public ApiResponse<List<ManualOrderDiagnosticService.Response>> history(@PathVariable String id){
        return ApiResponse.success(service.history(user.userId(),id),"저장된 진단 이력. KB 호출 없음");
    }
    @PostMapping public ApiResponse<ManualOrderDiagnosticService.Response> diagnose(@PathVariable String id,@Valid @RequestBody Request request){
        return ApiResponse.success(service.diagnose(user.userId(),id,request.diagnosticId(),request.orderNo(),request.acknowledged(),request.confirmation()),"읽기 전용 진단. 주문 상태·잠금 변경 없음");
    }
    public record Request(@NotBlank @Size(max=36) String diagnosticId,@NotBlank @Pattern(regexp="[0-9]{10}") String orderNo,
        boolean acknowledged,@NotBlank String confirmation){}
}
