package com.sagopalgo.api.alert.service;

import com.sagopalgo.api.alert.dto.AlertListResponse;
import com.sagopalgo.api.alert.dto.AlertResponse;
import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.dashboard.dto.DashboardAlertResponse;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 추천 결과를 사용자 알림으로 변환하고 Windows 앱 전달 상태를 관리합니다.
 */
@Service
public class AlertService {

    private static final int MAX_PAGE_SIZE = 100;
    private static final int MAX_PENDING_SIZE = 50;

    private final AlertMapper alertMapper;
    private final WatchlistMapper watchlistMapper;
    private final AlertProperties properties;

    public AlertService(
        AlertMapper alertMapper,
        WatchlistMapper watchlistMapper,
        AlertProperties properties
    ) {
        this.alertMapper = alertMapper;
        this.watchlistMapper = watchlistMapper;
        this.properties = properties;
    }

    @Transactional
    public Optional<AlertResponse> createFromRecommendation(StoredRecommendation stored) {
        RecommendationRecord recommendation = stored.recommendation();
        String alertType = alertType(recommendation.getStatus());
        if (alertType == null || !alertsEnabled(recommendation)) {
            return Optional.empty();
        }

        LocalDateTime cutoff = LocalDateTime.now().minusMinutes(
            Math.max(1, properties.getCooldownMinutes())
        );
        if (alertMapper.existsRecentSignal(
            recommendation.getUserId(),
            recommendation.getStockCode(),
            recommendation.getMarket(),
            alertType,
            cutoff
        )) {
            return Optional.empty();
        }

        AlertRecord record = new AlertRecord();
        record.setUserId(recommendation.getUserId());
        record.setRecommendationId(recommendation.getRecommendationId());
        record.setAlertType(alertType);
        record.setTitle(title(recommendation, alertType));
        record.setBody(limit(recommendation.getAiSummary(), 500));
        alertMapper.insert(record);
        return alertMapper.findByIdAndUserId(record.getAlertId(), recommendation.getUserId())
            .map(AlertResponse::from);
    }

    @Transactional(readOnly = true)
    public AlertListResponse findAll(Long userId, boolean unreadOnly, int page, int size) {
        validatePage(page, size);
        List<AlertResponse> items = alertMapper.findPage(userId, unreadOnly, size, page * size)
            .stream()
            .map(AlertResponse::from)
            .toList();
        return new AlertListResponse(items, page, size, alertMapper.count(userId, unreadOnly));
    }

    @Transactional(readOnly = true)
    public List<AlertResponse> findPending(Long userId, int limit) {
        int normalizedLimit = Math.min(Math.max(limit, 1), MAX_PENDING_SIZE);
        return alertMapper.findPending(userId, normalizedLimit)
            .stream()
            .map(AlertResponse::from)
            .toList();
    }

    @Transactional
    public AlertResponse markSent(Long userId, Long alertId) {
        if (alertMapper.markSent(alertId, userId) == 0) {
            throw notFound();
        }
        return findOne(userId, alertId);
    }

    @Transactional
    public AlertResponse markRead(Long userId, Long alertId) {
        if (alertMapper.markRead(alertId, userId) == 0) {
            throw notFound();
        }
        return findOne(userId, alertId);
    }

    @Transactional(readOnly = true)
    public List<DashboardAlertResponse> latestDashboardAlerts(Long userId) {
        return alertMapper.findPage(userId, false, 20, 0)
            .stream()
            .map(record -> new DashboardAlertResponse(
                record.getAlertId(),
                record.getTitle(),
                record.getBody(),
                AlertResponse.from(record).timeLabel(),
                record.getAlertType(),
                record.isRead()
            ))
            .toList();
    }

    private AlertResponse findOne(Long userId, Long alertId) {
        return alertMapper.findByIdAndUserId(alertId, userId)
            .map(AlertResponse::from)
            .orElseThrow(this::notFound);
    }

    private boolean alertsEnabled(RecommendationRecord recommendation) {
        return watchlistMapper.findAlertEnabledByUserStockAndMarket(
            recommendation.getUserId(),
            recommendation.getStockCode(),
            recommendation.getMarket()
        ).orElse(true);
    }

    private String alertType(String status) {
        return switch (status) {
            case "RISK", "STOP_LOSS_WATCH" -> "RISK";
            case "TAKE_PROFIT" -> "SELL";
            case "BUY_STRONG", "BUY_WATCH" -> "BUY";
            default -> null;
        };
    }

    private String title(RecommendationRecord recommendation, String alertType) {
        String signal = switch (alertType) {
            case "RISK" -> "위험 신호";
            case "SELL" -> "익절 검토";
            default -> "매수 후보";
        };
        return limit(recommendation.getStockName() + " " + signal, 100);
    }

    private String limit(String value, int maxLength) {
        if (value == null || value.isBlank()) {
            return "새 투자 분석 신호가 감지되었습니다. 앱에서 상세 근거를 확인하세요.";
        }
        return value.length() <= maxLength ? value : value.substring(0, maxLength);
    }

    private void validatePage(int page, int size) {
        if (page < 0 || size < 1 || size > MAX_PAGE_SIZE) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "알림 페이지는 0 이상, 크기는 1~100이어야 합니다.");
        }
    }

    private ApiException notFound() {
        return new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "알림을 찾을 수 없습니다.");
    }
}
