package com.sagopalgo.api.settings.dto;

import com.sagopalgo.api.order.dto.OrderReadinessResponse;
import java.util.List;

public record ProviderSettingsResponse(
    String secretStorageType,
    String secretStorageDescription,
    String orderSafetyMode,
    OrderReadinessResponse orderReadiness,
    List<String> marketDataFallbackOrder,
    String marketDataFallbackDescription,
    List<ProviderSettingResponse> providers
) {
}
