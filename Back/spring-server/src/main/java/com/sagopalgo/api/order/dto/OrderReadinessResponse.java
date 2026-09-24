package com.sagopalgo.api.order.dto;

import java.util.List;

public record OrderReadinessResponse(boolean canSubmit, List<OrderReadinessCheckResponse> checks) {
}
