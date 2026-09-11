package com.sagopalgo.api.settings.dto;

import java.util.List;

public record ProviderSettingsResponse(
    List<ProviderSettingResponse> providers
) {
}
