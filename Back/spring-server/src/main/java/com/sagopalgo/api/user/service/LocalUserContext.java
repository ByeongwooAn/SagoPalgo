package com.sagopalgo.api.user.service;

import com.sagopalgo.api.config.PersonalModeProperties;
import org.springframework.stereotype.Component;

/**
 * 개인용 프로그램에서 모든 사용자 데이터를 묶는 로컬 소유자 컨텍스트입니다.
 */
@Component
public class LocalUserContext {

    private final PersonalModeProperties personalModeProperties;

    public LocalUserContext(PersonalModeProperties personalModeProperties) {
        this.personalModeProperties = personalModeProperties;
    }

    public Long userId() {
        return personalModeProperties.userId();
    }
}
