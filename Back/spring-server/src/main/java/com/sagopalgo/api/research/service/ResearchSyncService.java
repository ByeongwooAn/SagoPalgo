package com.sagopalgo.api.research.service;

import com.sagopalgo.api.alert.service.EventAlertService;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.dto.ResearchProviderStatusResponse;
import com.sagopalgo.api.research.dto.ResearchSyncStatusResponse;
import java.time.LocalDate;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

/**
 * 수동·스케줄 동기화를 실행하고 같은 형식의 상태 기록을 남깁니다.
 */
@Service
public class ResearchSyncService {

    private static final Logger log = LoggerFactory.getLogger(ResearchSyncService.class);

    public static final String MANUAL = "MANUAL";
    public static final String SCHEDULED = "SCHEDULED";

    private final ResearchFeedService researchFeedService;
    private final ResearchSyncStatusStore statusStore;
    private final ResearchProviderProperties properties;
    private final EventAlertService eventAlertService;

    public ResearchSyncService(
        ResearchFeedService researchFeedService,
        ResearchSyncStatusStore statusStore,
        ResearchProviderProperties properties,
        EventAlertService eventAlertService
    ) {
        this.researchFeedService = researchFeedService;
        this.statusStore = statusStore;
        this.properties = properties;
        this.eventAlertService = eventAlertService;
    }

    public ResearchFeedResponse sync(
        Long userId,
        String stockCode,
        String stockName,
        LocalDate fromDate,
        LocalDate toDate,
        String triggerType
    ) {
        ResearchFeedResponse response;
        try {
            response = researchFeedService.syncFeed(
                stockCode,
                stockName,
                fromDate,
                toDate
            );
        } catch (RuntimeException exception) {
            try {
                statusStore.save(
                    userId,
                    stockCode,
                    stockName,
                    triggerType,
                    "FAILED",
                    0,
                    0,
                    0,
                    1,
                    0,
                    exception.getMessage()
                );
            } catch (RuntimeException statusException) {
                exception.addSuppressed(statusException);
            }
            throw exception;
        }
        saveResponse(userId, triggerType, response);
        createResearchAlerts(userId, response);
        return response;
    }

    public ResearchSyncStatusResponse getStatus(Long userId, String stockCode) {
        ResearchProviderProperties.Sync sync = properties.getSync();
        return new ResearchSyncStatusResponse(
            sync.isEnabled(),
            sync.getCron(),
            sync.getZone(),
            statusStore.find(userId, stockCode).orElse(null)
        );
    }

    private void saveResponse(Long userId, String triggerType, ResearchFeedResponse response) {
        int succeeded = count(response, "SUCCESS");
        int failed = count(response, "FAILED");
        int disabled = count(response, "DISABLED");
        String status = resultStatus(succeeded, failed);
        String message = "Provider 성공 %d · 실패 %d · 비활성 %d".formatted(succeeded, failed, disabled);
        statusStore.save(
            userId,
            response.stockCode(),
            response.stockName(),
            triggerType,
            status,
            response.news().size(),
            response.disclosures().size(),
            succeeded,
            failed,
            disabled,
            message
        );
    }

    private void createResearchAlerts(Long userId, ResearchFeedResponse response) {
        try {
            eventAlertService.createResearchAlerts(
                userId,
                response.stockCode(),
                response.stockName(),
                response.news() == null ? List.of() : response.news(),
                response.disclosures() == null ? List.of() : response.disclosures()
            );
        } catch (RuntimeException exception) {
            log.warn(
                "뉴스·공시 알림 생성 실패. stockCode={} message={}",
                response.stockCode(),
                exception.getMessage()
            );
        }
    }

    private int count(ResearchFeedResponse response, String status) {
        return (int) response.providers()
            .stream()
            .map(ResearchProviderStatusResponse::status)
            .filter(status::equals)
            .count();
    }

    private String resultStatus(int succeeded, int failed) {
        if (failed > 0 && succeeded > 0) {
            return "PARTIAL";
        }
        if (failed > 0) {
            return "FAILED";
        }
        if (succeeded > 0) {
            return "SUCCESS";
        }
        return "SKIPPED";
    }
}
