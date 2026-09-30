package com.sagopalgo.api.alert.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.alert.dto.AlertResponse;
import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import com.sagopalgo.api.recommendation.model.StoredRecommendation;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class AlertServiceTest {

    @Mock
    private AlertMapper alertMapper;

    @Mock
    private WatchlistMapper watchlistMapper;

    private AlertService service;

    @BeforeEach
    void setUp() {
        AlertProperties properties = new AlertProperties();
        properties.setCooldownMinutes(60);
        service = new AlertService(alertMapper, watchlistMapper, properties);
    }

    @Test
    @DisplayName("위험 추천을 Windows 전달 대기 알림으로 저장한다")
    void createsRiskAlertFromRecommendation() {
        StoredRecommendation stored = stored("STOP_LOSS_WATCH");
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentSignal(any(), any(), any(), any(), any())).thenReturn(false);
        when(alertMapper.insert(any())).thenAnswer(invocation -> {
            AlertRecord record = invocation.getArgument(0);
            record.setAlertId(7L);
            return 1;
        });
        when(alertMapper.findByIdAndUserId(7L, 1L)).thenAnswer(invocation -> {
            AlertRecord record = new AlertRecord();
            record.setAlertId(7L);
            record.setUserId(1L);
            record.setRecommendationId(99L);
            record.setAlertType("RISK");
            record.setTitle("삼성전자 위험 신호");
            record.setBody("손절 기준에 도달했습니다.");
            record.setCreatedAt(LocalDateTime.now());
            return Optional.of(record);
        });

        Optional<AlertResponse> response = service.createFromRecommendation(stored);

        assertThat(response).isPresent();
        assertThat(response.orElseThrow().type()).isEqualTo("RISK");
        assertThat(response.orElseThrow().sentAt()).isNull();
        verify(alertMapper).insert(any(AlertRecord.class));
    }

    @Test
    @DisplayName("관심 종목 알림이 꺼져 있으면 추천 알림을 만들지 않는다")
    void skipsDisabledWatchlistAlert() {
        StoredRecommendation stored = stored("BUY_WATCH");
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(false));

        assertThat(service.createFromRecommendation(stored)).isEmpty();
        verify(alertMapper, never()).insert(any());
    }

    @Test
    @DisplayName("같은 종목과 신호가 쿨다운 안에 있으면 중복 알림을 만들지 않는다")
    void skipsRecentDuplicateSignal() {
        StoredRecommendation stored = stored("TAKE_PROFIT");
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.empty());
        when(alertMapper.existsRecentSignal(any(), any(), any(), any(), any())).thenReturn(true);

        assertThat(service.createFromRecommendation(stored)).isEmpty();
        verify(alertMapper, never()).insert(any());
    }

    @Test
    @DisplayName("보유 유지 추천은 사용자 알림 대상이 아니다")
    void skipsHoldRecommendation() {
        assertThat(service.createFromRecommendation(stored("HOLD"))).isEmpty();
        verify(alertMapper, never()).insert(any());
    }

    @Test
    void pendingAlertsUseUserScopedCursorAndBoundedLimit() {
        when(alertMapper.findPending(1L, 50, 12L)).thenReturn(List.of());

        assertThat(service.findPending(1L, 100, 12L)).isEmpty();

        verify(alertMapper).findPending(1L, 50, 12L);
    }

    @Test
    void pendingAlertsRejectNegativeCursor() {
        assertThatThrownBy(() -> service.findPending(1L, 20, -1L))
            .isInstanceOf(com.sagopalgo.api.common.exception.ApiException.class);
        verify(alertMapper, never()).findPending(any(), anyInt(), any());
    }

    private StoredRecommendation stored(String status) {
        RecommendationRecord record = new RecommendationRecord();
        record.setRecommendationId(99L);
        record.setUserId(1L);
        record.setStockCode("005930");
        record.setStockName("삼성전자");
        record.setMarket("KOSPI");
        record.setStatus(status);
        record.setAiSummary("손절 기준에 도달했습니다.");
        return new StoredRecommendation(record, List.of());
    }
}
