package com.sagopalgo.api.settings.dto;

import java.util.List;

public record ProviderSettingsResponse(
    String secretStorageType,
    String secretStorageDescription,
    String orderSafetyMode,
    List<ProviderSettingResponse> providers
) {
}
