package com.sagopalgo.api.alert.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.alert.model.PortfolioPosition;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class PortfolioRiskAlertServiceTest {

    @Mock
    private AlertMapper alertMapper;

    @Mock
    private WatchlistMapper watchlistMapper;

    @Mock
    private CapitalService capitalService;

    private AlertProperties properties;
    private PortfolioRiskAlertService service;

    @BeforeEach
    void setUp() {
        properties = new AlertProperties();
        properties.setCooldownMinutes(60);
        service = new PortfolioRiskAlertService(
            alertMapper,
            watchlistMapper,
            capitalService,
            properties
        );
    }

    @Test
    @DisplayName("종목 최대 비중과 전체 손실 한도를 넘으면 두 위험 알림을 생성한다")
    void createsOverweightAndTotalLossAlerts() {
        when(capitalService.findByUserId(1L)).thenReturn(capital());
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentEvent(any(), any(), any(), any(), any())).thenReturn(false);
        when(alertMapper.existsRecentPortfolioEvent(any(), any(), any())).thenReturn(false);
        when(alertMapper.insertEvent(any())).thenReturn(1);

        int created = service.createAlerts(1L, List.of(position("KB", "900")));

        assertThat(created).isEqualTo(2);
        ArgumentCaptor<AlertRecord> captor = ArgumentCaptor.forClass(AlertRecord.class);
        verify(alertMapper, org.mockito.Mockito.times(2)).insertEvent(captor.capture());
        assertThat(captor.getAllValues())
            .extracting(AlertRecord::getEventType)
            .containsExactly("PORTFOLIO_POSITION_OVERWEIGHT", "PORTFOLIO_TOTAL_LOSS");
        assertThat(captor.getAllValues()).extracting(AlertRecord::getAlertType)
            .containsOnly("PORTFOLIO");
    }

    @Test
    @DisplayName("fallback 시세는 비용 기준 비중 경고에 쓰되 전체 손실 계산에서는 제외한다")
    void fallbackCreatesOnlyOverweightAlert() {
        when(capitalService.findByUserId(1L)).thenReturn(capital());
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentEvent(any(), any(), any(), any(), any())).thenReturn(false);
        when(alertMapper.insertEvent(any())).thenReturn(1);

        int created = service.createAlerts(1L, List.of(position("FALLBACK", "1000")));

        assertThat(created).isEqualTo(1);
        ArgumentCaptor<AlertRecord> captor = ArgumentCaptor.forClass(AlertRecord.class);
        verify(alertMapper).insertEvent(captor.capture());
        assertThat(captor.getValue().getEventType()).isEqualTo("PORTFOLIO_POSITION_OVERWEIGHT");
        verify(alertMapper, never()).existsRecentPortfolioEvent(any(), any(), any());
    }

    @Test
    @DisplayName("쿨다운 안에 발생한 포트폴리오 위험 이벤트는 중복 생성하지 않는다")
    void skipsEventsDuringCooldown() {
        when(capitalService.findByUserId(1L)).thenReturn(capital());
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentEvent(any(), any(), any(), any(), any())).thenReturn(true);
        when(alertMapper.existsRecentPortfolioEvent(any(), any(), any())).thenReturn(true);

        assertThat(service.createAlerts(1L, List.of(position("KB", "900")))).isZero();
        verify(alertMapper, never()).insertEvent(any());
    }

    @Test
    @DisplayName("포트폴리오 이벤트 설정이 꺼져 있으면 평가하지 않는다")
    void skipsWhenDisabled() {
        properties.setPortfolioEventsEnabled(false);

        assertThat(service.createAlerts(1L, List.of(position("KB", "900")))).isZero();
        verify(capitalService, never()).findByUserId(any());
    }

    private CapitalResponse capital() {
        return new CapitalResponse(
            new BigDecimal("1000000"),
            new BigDecimal("100000"),
            new BigDecimal("200000"),
            new BigDecimal("0.02")
        );
    }

    private PortfolioPosition position(String provider, String currentPrice) {
        Holding holding = new Holding();
        holding.setUserId(1L);
        holding.setStockCode("005930");
        holding.setStockName("삼성전자");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("1000"));
        holding.setQuantity(new BigDecimal("300"));

        StockQuote quote = new StockQuote(
            provider, "005930", "삼성전자", "KOSPI",
            new BigDecimal(currentPrice), BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, Instant.now()
        );
        return new PortfolioPosition(holding, quote);
    }
}
