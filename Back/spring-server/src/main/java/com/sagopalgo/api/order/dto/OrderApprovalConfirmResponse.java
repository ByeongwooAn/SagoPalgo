package com.sagopalgo.api.order.dto;

public record OrderApprovalConfirmResponse(Long approvalId, String status, boolean orderSubmitted, String message) {
}
