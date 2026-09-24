package com.sagopalgo.api.order.dto;

public record OrderReadinessCheckResponse(String code, boolean passed, String message) {
}
