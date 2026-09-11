package com.sagopalgo.api.user.service;

import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.user.mapper.UserMapper;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

/**
 * 개인용 모드에서 기존 사용자 FK 구조가 동작하도록 로컬 소유자 행을 준비합니다.
 */
@Component
public class PersonalModeInitializer implements ApplicationRunner {

    private final PersonalModeProperties personalModeProperties;
    private final UserMapper userMapper;

    public PersonalModeInitializer(
        PersonalModeProperties personalModeProperties,
        UserMapper userMapper
    ) {
        this.personalModeProperties = personalModeProperties;
        this.userMapper = userMapper;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!personalModeProperties.enabled()) {
            return;
        }

        userMapper.ensureLocalOwner(
            personalModeProperties.userId(),
            personalModeProperties.email(),
            personalModeProperties.nickname()
        );
    }
}
