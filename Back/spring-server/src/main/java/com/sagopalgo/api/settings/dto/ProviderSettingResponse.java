package com.sagopalgo.api.settings.dto;

public record ProviderSettingResponse(
    String code,
    String displayName,
    boolean marketDataEnabled,
    boolean accountEnabled,
    boolean orderEnabled,
    boolean configured,
    String roleDescription
) {
}
