package com.sagopalgo.api.order.model;
import java.time.LocalDateTime;
public record ManualOrderDiagnosticRecord(String diagnosticId,String commandId,Long userId,String orderNo,
    String phaseBefore,String state,String reportJson,LocalDateTime createdAt,LocalDateTime completedAt){}
