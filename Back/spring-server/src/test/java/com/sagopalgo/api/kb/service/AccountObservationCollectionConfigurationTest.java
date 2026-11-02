package com.sagopalgo.api.kb.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import com.sagopalgo.api.config.AccountObservationCollectionProperties;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

class AccountObservationCollectionConfigurationTest {
    private final ApplicationContextRunner runner=new ApplicationContextRunner().withUserConfiguration(Config.class);

    @Test void defaultOffDoesNotRegisterSchedulerAndUsesFifteenMinuteInterval() {
        runner.run(context -> {
            assertThat(context).hasNotFailed().doesNotHaveBean(AccountObservationCollectionScheduler.class);
            var policy=context.getBean(AccountObservationCollectionProperties.class);
            assertThat(policy.enabled()).isFalse();assertThat(policy.intervalSeconds()).isEqualTo(900);
            verifyNoInteractions(context.getBean(AccountObservationCollectionService.class));
        });
    }
    @Test void enabledConfigurationRegistersSchedulerButContextCreationDoesNotCollect() {
        runner.withPropertyValues("sagopalgo.account-observation.collection.enabled=true").run(context -> {
            assertThat(context).hasSingleBean(AccountObservationCollectionScheduler.class);
            var service=context.getBean(AccountObservationCollectionService.class);verifyNoInteractions(service);
            context.getBean(AccountObservationCollectionScheduler.class).tick();verify(service).collectDue();
        });
    }
    @ParameterizedTest @ValueSource(ints={0,59,86401})
    void invalidIntervalsFailBindingRatherThanStartingFastPolling(int value) {
        runner.withPropertyValues("sagopalgo.account-observation.collection.interval-seconds="+value)
            .run(context -> assertThat(context).hasFailed());
    }
    @ParameterizedTest @ValueSource(ints={60,86400})
    void documentedIntervalBoundsBind(int value) {
        runner.withPropertyValues("sagopalgo.account-observation.collection.interval-seconds="+value).run(context ->
            assertThat(context.getBean(AccountObservationCollectionProperties.class).intervalSeconds()).isEqualTo(value));
    }
    @Configuration(proxyBeanMethods=false)
    @EnableConfigurationProperties(AccountObservationCollectionProperties.class)
    @Import(AccountObservationCollectionScheduler.class)
    static class Config {
        @Bean AccountObservationCollectionService service() {return mock(AccountObservationCollectionService.class);}
    }
}
