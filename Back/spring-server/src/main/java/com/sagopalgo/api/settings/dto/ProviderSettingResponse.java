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
    String roleDescription,
    boolean accountConfigured
) {
    public ProviderSettingResponse(String code, String displayName, boolean marketDataEnabled,
        boolean accountEnabled, boolean orderEnabled, boolean newsEnabled, boolean disclosureEnabled,
        boolean configured, List<String> missingRequiredSettings, String roleDescription) {
        this(code, displayName, marketDataEnabled, accountEnabled, orderEnabled, newsEnabled,
            disclosureEnabled, configured, missingRequiredSettings, roleDescription, accountEnabled && configured);
    }
}
