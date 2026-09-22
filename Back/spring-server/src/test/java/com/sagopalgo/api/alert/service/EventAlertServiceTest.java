package com.sagopalgo.api.alert.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.alert.mapper.AlertMapper;
import com.sagopalgo.api.alert.model.AlertRecord;
import com.sagopalgo.api.config.AlertProperties;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
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
class EventAlertServiceTest {

    @Mock
    private AlertMapper alertMapper;

    @Mock
    private WatchlistMapper watchlistMapper;

    private EventAlertService service;

    @BeforeEach
    void setUp() {
        AlertProperties properties = new AlertProperties();
        properties.setCooldownMinutes(60);
        properties.setVolatilityThresholdRate(new BigDecimal("5"));
        service = new EventAlertService(alertMapper, watchlistMapper, properties);
    }

    @Test
    @DisplayName("익절 기준과 급등 기준을 만족하면 전용 가격 알림을 생성한다")
    void createsTakeProfitAndSurgeAlerts() {
        Holding holding = holding();
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentEvent(any(), any(), any(), any(), any())).thenReturn(false);
        when(alertMapper.insertEvent(any())).thenReturn(1);

        int created = service.createPriceAlerts(holding, quote("KB", "112000", "6.2"));

        assertThat(created).isEqualTo(2);
        ArgumentCaptor<AlertRecord> captor = ArgumentCaptor.forClass(AlertRecord.class);
        verify(alertMapper, org.mockito.Mockito.times(2)).insertEvent(captor.capture());
        assertThat(captor.getAllValues())
            .extracting(AlertRecord::getEventType)
            .containsExactly("PRICE_TAKE_PROFIT", "PRICE_SURGE");
    }

    @Test
    @DisplayName("쿨다운 안에 같은 가격 이벤트가 있으면 다시 생성하지 않는다")
    void skipsPriceEventDuringCooldown() {
        Holding holding = holding();
        when(watchlistMapper.findAlertEnabledByUserStockAndMarket(1L, "005930", "KOSPI"))
            .thenReturn(Optional.of(true));
        when(alertMapper.existsRecentEvent(any(), any(), any(), any(), any())).thenReturn(true);

        assertThat(service.createPriceAlerts(holding, quote("KB", "100000", "6"))).isZero();
        verify(alertMapper, never()).insertEvent(any());
    }

    @Test
    @DisplayName("fallback 시세로는 가격 이벤트 알림을 만들지 않는다")
    void skipsFallbackQuote() {
        assertThat(service.createPriceAlerts(holding(), quote("FALLBACK", "112000", "6"))).isZero();
        verify(alertMapper, never()).insertEvent(any());
    }

    @Test
    @DisplayName("신규 뉴스와 공시는 고유 이벤트 키로 한 번만 저장한다")
    void createsResearchAlertsWithStableEventKeys() {
        NewsArticle article = new NewsArticle(
            "NAVER_NEWS", "005930", "삼성전자 실적 개선", "https://news.example/1",
            "요약", Instant.now()
        );
        Disclosure disclosure = new Disclosure(
            "OPEN_DART", "005930", "00126380", "삼성전자", "단일판매 공급계약",
            "20260922000123", "삼성전자", LocalDate.now(), "https://dart.example/1"
        );
        when(watchlistMapper.findAlertEnabledByUserAndStockCode(1L, "005930"))
            .thenReturn(Optional.of(true));
        when(alertMapper.insertEvent(any())).thenReturn(1, 1, 0, 0);

        int first = service.createResearchAlerts(
            1L, "005930", "삼성전자", List.of(article), List.of(disclosure)
        );
        int second = service.createResearchAlerts(
            1L, "005930", "삼성전자", List.of(article), List.of(disclosure)
        );

        assertThat(first).isEqualTo(2);
        assertThat(second).isZero();
        ArgumentCaptor<AlertRecord> captor = ArgumentCaptor.forClass(AlertRecord.class);
        verify(alertMapper, org.mockito.Mockito.times(4)).insertEvent(captor.capture());
        List<AlertRecord> records = captor.getAllValues();
        assertThat(records).extracting(AlertRecord::getEventType)
            .containsExactly("NEWS", "DISCLOSURE", "NEWS", "DISCLOSURE");
        assertThat(records.get(0).getEventKey()).isEqualTo(records.get(2).getEventKey());
        assertThat(records.get(1).getEventKey()).isEqualTo(records.get(3).getEventKey());
    }

    @Test
    @DisplayName("오래된 뉴스와 공시는 새 이벤트 알림 대상에서 제외한다")
    void skipsOldResearchEvents() {
        NewsArticle article = new NewsArticle(
            "NAVER_NEWS", "005930", "오래된 뉴스", "https://news.example/old",
            "요약", Instant.now().minusSeconds(48 * 60 * 60)
        );
        Disclosure disclosure = new Disclosure(
            "OPEN_DART", "005930", "00126380", "삼성전자", "오래된 공시",
            "20260901000123", "삼성전자", LocalDate.now().minusDays(3), "https://dart.example/old"
        );
        when(watchlistMapper.findAlertEnabledByUserAndStockCode(1L, "005930"))
            .thenReturn(Optional.of(true));

        assertThat(service.createResearchAlerts(
            1L, "005930", "삼성전자", List.of(article), List.of(disclosure)
        )).isZero();
        verify(alertMapper, never()).insertEvent(any());
    }

    private Holding holding() {
        Holding holding = new Holding();
        holding.setUserId(1L);
        holding.setStockCode("005930");
        holding.setStockName("삼성전자");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("100000"));
        holding.setStopLossRate(new BigDecimal("-5"));
        holding.setTakeProfitRate(new BigDecimal("10"));
        return holding;
    }

    private StockQuote quote(String provider, String currentPrice, String changeRate) {
        return new StockQuote(
            provider, "005930", "삼성전자", "KOSPI",
            new BigDecimal(currentPrice), BigDecimal.ZERO, new BigDecimal(changeRate),
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
            BigDecimal.ZERO, Instant.now()
        );
    }
}
