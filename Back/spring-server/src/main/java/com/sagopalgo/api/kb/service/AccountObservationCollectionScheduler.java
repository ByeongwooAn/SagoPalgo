package com.sagopalgo.api.kb.service;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import java.time.Duration;
import java.time.Instant;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix="sagopalgo.account-observation.collection",name="enabled",havingValue="true")
public class AccountObservationCollectionScheduler {
    private final AccountObservationCollectionService service;
    private final ThreadPoolTaskScheduler scheduler=new ThreadPoolTaskScheduler();
    public AccountObservationCollectionScheduler(AccountObservationCollectionService service) {this.service=service;}

    // 장시간 호출 후 누락된 과거 주기를 몰아서 실행하지 않습니다. 실제 due 판정은 DB UTC입니다.
    public void tick() {service.collectDue();}

    /** 컨텍스트 공용 TaskScheduler Bean으로 노출하지 않아 기존 알림/뉴스 실행기를 바꾸지 않습니다. */
    @PostConstruct
    void start() {
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("account-observation-");
        scheduler.setDaemon(true);
        scheduler.setWaitForTasksToCompleteOnShutdown(false);
        scheduler.initialize();
        scheduler.scheduleWithFixedDelay(this::tick,Instant.now().plusSeconds(60),Duration.ofSeconds(60));
    }

    @PreDestroy
    void stop() {scheduler.shutdown();}
}
