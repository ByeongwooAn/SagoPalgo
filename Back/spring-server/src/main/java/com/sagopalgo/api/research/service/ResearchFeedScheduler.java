package com.sagopalgo.api.research.service;

import com.sagopalgo.api.config.PersonalModeProperties;
import com.sagopalgo.api.watchlist.dto.WatchlistResponse;
import com.sagopalgo.api.watchlist.service.WatchlistService;
import java.util.concurrent.atomic.AtomicBoolean;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 개인 사용자의 관심 종목을 순회하며 뉴스와 공시를 주기적으로 동기화합니다.
 */
@Component
@ConditionalOnProperty(
    prefix = "sagopalgo.research.sync",
    name = "enabled",
    havingValue = "true"
)
public class ResearchFeedScheduler {

    private static final Logger log = LoggerFactory.getLogger(ResearchFeedScheduler.class);

    private final WatchlistService watchlistService;
    private final ResearchSyncService researchSyncService;
    private final PersonalModeProperties personalModeProperties;
    private final AtomicBoolean running = new AtomicBoolean(false);

    public ResearchFeedScheduler(
        WatchlistService watchlistService,
        ResearchSyncService researchSyncService,
        PersonalModeProperties personalModeProperties
    ) {
        this.watchlistService = watchlistService;
        this.researchSyncService = researchSyncService;
        this.personalModeProperties = personalModeProperties;
    }

    @Scheduled(
        cron = "${sagopalgo.research.sync.cron:0 0/30 * * * *}",
        zone = "${sagopalgo.research.sync.zone:Asia/Seoul}"
    )
    public void syncWatchlist() {
        if (!personalModeProperties.enabled() || personalModeProperties.userId() == null) {
            log.warn("개인용 사용자 설정이 없어 관심 종목 자동 동기화를 건너뜁니다.");
            return;
        }
        if (!running.compareAndSet(false, true)) {
            log.info("이전 관심 종목 동기화가 실행 중이어서 이번 실행을 건너뜁니다.");
            return;
        }

        try {
            for (WatchlistResponse item : watchlistService.findAll(personalModeProperties.userId())) {
                syncItem(item);
            }
        } finally {
            running.set(false);
        }
    }

    private void syncItem(WatchlistResponse item) {
        try {
            researchSyncService.sync(
                personalModeProperties.userId(),
                item.stockCode(),
                item.stockName(),
                null,
                null,
                ResearchSyncService.SCHEDULED
            );
        } catch (RuntimeException exception) {
            log.warn(
                "관심 종목 뉴스·공시 자동 동기화 실패. stockCode={} message={}",
                item.stockCode(),
                exception.getMessage()
            );
        }
    }
}
