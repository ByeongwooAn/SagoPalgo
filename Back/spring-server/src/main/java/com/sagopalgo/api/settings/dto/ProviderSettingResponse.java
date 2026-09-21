package com.sagopalgo.api.settings.dto;

import java.util.List;

public record ProviderSettingResponse(
    String code,
    String displayName,
    boolean marketDataEnabled,
    boolean accountEnabled,
    boolean orderEnabled,
    boolean newsEnabled,
    boolean disclosureEnabled,
    boolean configured,
    List<String> missingRequiredSettings,
    String roleDescription
) {
}
