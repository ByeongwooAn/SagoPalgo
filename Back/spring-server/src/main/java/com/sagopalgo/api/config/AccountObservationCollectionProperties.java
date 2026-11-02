package com.sagopalgo.api.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

/** 수집 간격은 기술적 하한이며 공급자 허용 한도를 뜻하지 않습니다. 기본 OFF입니다. */
@ConfigurationProperties(prefix="sagopalgo.account-observation.collection")
public record AccountObservationCollectionProperties(boolean enabled, @DefaultValue("900") int intervalSeconds) {
    public AccountObservationCollectionProperties {
        if (intervalSeconds < 60 || intervalSeconds > 86400) {
            throw new IllegalArgumentException("계좌 관찰 수집 간격은 60~86400초여야 합니다.");
        }
    }
}
