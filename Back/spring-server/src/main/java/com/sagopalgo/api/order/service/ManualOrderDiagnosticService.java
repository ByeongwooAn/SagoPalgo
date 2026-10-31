package com.sagopalgo.api.order.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import java.time.LocalDateTime;
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

/** 증권사 조회만 수행하고 SENDING/반환 결과/제출 가드/포트폴리오는 변경하지 않습니다. */
@Service
public class ManualOrderDiagnosticService {
    private final ManualOrderMapper commands;
    private final ManualOrderDiagnosticMapper diagnostics;
    private final ManualOrderDiagnosticStore store;
    private final KbOrderExecutionService executions;
    private final ObjectMapper json;
    public ManualOrderDiagnosticService(ManualOrderMapper commands,ManualOrderDiagnosticMapper diagnostics,
        ManualOrderDiagnosticStore store,KbOrderExecutionService executions,ObjectMapper json) {
        this.commands=commands;this.diagnostics=diagnostics;this.store=store;this.executions=executions;this.json=json;
    }
    public List<Response> history(Long user,String commandId) {
        storage();
        if(commands.find(commandId,user)==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        try{return diagnostics.recent(commandId,user).stream().map(this::response).toList();}
        catch(DataAccessException exception){throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);}
    }
    public Response diagnose(Long user,String commandId,String id,String orderNo,boolean acknowledged,String confirmation) {
        OrderSendingDiagnosticRules.validate(id,orderNo,acknowledged,confirmation);
        storage();
        try {
            var claim=store.claim(user,commandId,id,orderNo);
            if(!claim.claimed()) return response(claim.record());
            var c=claim.command();
            OrderSendingDiagnosticRules.Report report;
            try {
                var lookup=executions.findByOrderNumber(c.orderDate(),orderNo);
                report=OrderSendingDiagnosticRules.evaluate(new OrderPrecheckRequest(c.stockCode(),c.stockName(),c.market(),c.side(),c.price(),c.quantity()),
                    c.kind(),c.orderDate(),c.createdAt(),orderNo,lookup);
            } catch(RuntimeException exception){report=OrderSendingDiagnosticRules.failure("LOOKUP_FAILED");}
            return response(store.complete(user,commandId,id,report));
        } catch(DataAccessException exception){throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);}
    }
    private void storage() {
        try {commands.verifyStorage();}
        catch(DataAccessException exception){throw new ApiException(ErrorCode.ORDER_STORAGE_UNAVAILABLE);}
        try {diagnostics.verifyStorage();}
        catch(DataAccessException exception){throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);}
    }
    private Response response(ManualOrderDiagnosticRecord row) {
        try {
            return new Response(row.diagnosticId(),row.commandId(),row.orderNo(),row.phaseBefore(),row.state(),
                row.reportJson()==null?null:json.readValue(row.reportJson(),OrderSendingDiagnosticRules.Report.class),row.createdAt(),row.completedAt());
        } catch(JsonProcessingException exception){throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);}
    }
    public record Response(String diagnosticId,String commandId,String orderNo,String phaseBefore,String state,
        OrderSendingDiagnosticRules.Report report,LocalDateTime createdAt,LocalDateTime completedAt){}
}
