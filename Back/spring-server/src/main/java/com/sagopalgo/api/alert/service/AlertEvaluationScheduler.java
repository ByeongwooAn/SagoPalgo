package com.sagopalgo.api.alert.service;

import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.holding.service.HoldingService;
import com.sagopalgo.api.recommendation.service.RecommendationService;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Ubuntu 백엔드에서 보유 종목을 주기적으로 재분석해 새 알림 신호를 만듭니다.
 */
@Component
@ConditionalOnProperty(
    prefix = "sagopalgo.alerts",
    name = "analysis-enabled",
    havingValue = "true"
)
public class AlertEvaluationScheduler {

    private static final Logger log = LoggerFactory.getLogger(AlertEvaluationScheduler.class);

    private final HoldingService holdingService;
    private final RecommendationService recommendationService;
    private final PersonalModeProperties personalModeProperties;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public AlertEvaluationScheduler(
        HoldingService holdingService,
        RecommendationService recommendationService,
        PersonalModeProperties personalModeProperties
    ) {
        this.holdingService = holdingService;
        this.recommendationService = recommendationService;
        this.personalModeProperties = personalModeProperties;
    }

    @Scheduled(
        cron = "${sagopalgo.alerts.cron:0 0/15 * * * *}",
        zone = "${sagopalgo.alerts.zone:Asia/Seoul}"
    )
    public void analyzeHoldings() {
        Long userId = personalModeProperties.userId();
        if (!personalModeProperties.enabled() || userId == null) {
            log.warn("개인용 사용자 설정이 없어 알림 분석을 건너뜁니다.");
            return;
        }
        if (!running.compareAndSet(false, true)) {
            log.info("이전 알림 분석이 실행 중이어서 이번 실행을 건너뜁니다.");
            return;
        }

        try {
            for (Long holdingId : holdingService.findActiveIds(userId)) {
                analyzeOne(userId, holdingId);
            }
        } finally {
            running.set(false);
        }
    }

    private void analyzeOne(Long userId, Long holdingId) {
        try {
            recommendationService.analyzeHolding(userId, holdingId);
        } catch (RuntimeException exception) {
            log.warn(
                "보유 종목 알림 분석 실패. holdingId={} message={}",
                holdingId,
                exception.getMessage()
            );
        }
    }
}
