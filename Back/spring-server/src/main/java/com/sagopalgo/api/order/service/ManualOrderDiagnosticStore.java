package com.sagopalgo.api.order.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.order.mapper.*;
import com.sagopalgo.api.order.model.*;
import java.time.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** KB 조회 중에는 DB 잠금을 유지하지 않습니다. 진단 테이블 외에는 쓰지 않습니다. */
@Service
public class ManualOrderDiagnosticStore {
    private final ManualOrderMapper commands;
    private final ManualOrderDispatchMapper dispatches;
    private final ManualOrderDiagnosticMapper diagnostics;
    private final OrderAccountBinding binding;
    private final ObjectMapper json;
    public ManualOrderDiagnosticStore(ManualOrderMapper commands,ManualOrderDispatchMapper dispatches,
        ManualOrderDiagnosticMapper diagnostics,OrderAccountBinding binding,ObjectMapper json) {
        this.commands=commands;this.dispatches=dispatches;this.diagnostics=diagnostics;this.binding=binding;this.json=json;
    }
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public Claim claim(Long user,String commandId,String id,String orderNo) {
        var command=lock(user,commandId);
        var previous=diagnostics.find(id,user);
        if(previous!=null) {
            if(!commandId.equals(previous.commandId()) || !orderNo.equals(previous.orderNo())) {
                throw new ApiException(ErrorCode.VALIDATION_ERROR,"같은 진단 ID의 조회 대상을 바꿀 수 없습니다.");
            }
            return new Claim(previous,command,false);
        }
        var phase=phase(dispatches.lock(commandId,user));
        OrderSendingDiagnosticRules.requireCandidate(command.status(),phase);
        if(!binding.matches(command.accountFingerprint())) throw new ApiException(ErrorCode.VALIDATION_ERROR,"승인 당시 계좌 설정과 다릅니다.");
        var record=new ManualOrderDiagnosticRecord(id,commandId,user,orderNo,phase,"REQUESTED",null,now(),null);
        if(diagnostics.insert(record)!=1) throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);
        return new Claim(record,command,true);
    }
    @Transactional(propagation=Propagation.REQUIRES_NEW)
    public ManualOrderDiagnosticRecord complete(Long user,String commandId,String id,OrderSendingDiagnosticRules.Report report) {
        var command=lock(user,commandId);
        var record=diagnostics.find(id,user);
        if(record==null || !commandId.equals(record.commandId())) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        if("COMPLETED".equals(record.state())) return record;
        var phase=phase(dispatches.lock(commandId,user));
        var result=report.after(phase,command.status(),binding.matches(command.accountFingerprint()));
        try {
            if(diagnostics.complete(id,user,json.writeValueAsString(result),now())!=1) throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);
        } catch(JsonProcessingException exception){throw new ApiException(ErrorCode.DIAGNOSTIC_STORAGE_UNAVAILABLE);}
        return diagnostics.find(id,user);
    }
    private ManualOrderCommand lock(Long user,String commandId) {
        if(commands.lockUser(user)==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        var command=commands.lockCommand(commandId,user);
        if(command==null) throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND);
        return command;
    }
    private static String phase(ManualOrderDispatchRecord record){return record==null?"LEGACY_UNVERIFIED":record.phase();}
    private static LocalDateTime now(){return LocalDateTime.now(ZoneId.of("Asia/Seoul"));}
    public record Claim(ManualOrderDiagnosticRecord record,ManualOrderCommand command,boolean claimed){}
}
