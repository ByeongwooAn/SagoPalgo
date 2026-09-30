package com.sagopalgo.api.holding.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.capital.service.CapitalService;
import com.sagopalgo.api.capital.dto.CapitalResponse;
import com.sagopalgo.api.holding.dto.PortfolioCostExposure;
import com.sagopalgo.api.holding.dto.HoldingsListResponse;
import com.sagopalgo.api.holding.mapper.HoldingMapper;
import com.sagopalgo.api.holding.model.Holding;
import com.sagopalgo.api.market.service.MarketPriceService;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class HoldingServiceTest {

    @Mock
    private HoldingMapper holdingMapper;

    @Mock
    private CapitalService capitalService;

    @Mock
    private MarketPriceService marketPriceService;

    private HoldingService service;

    @BeforeEach
    void setUp() {
        service = new HoldingService(holdingMapper, capitalService, marketPriceService);
    }

    @Test
    @DisplayName("전체 미실현 손실이 허용 한도와 같으면 위험 사용률은 1이다")
    void calculatesPortfolioRiskUsageRate() {
        Holding holding = holding();
        when(holdingMapper.findActiveByUserId(1L)).thenReturn(List.of(holding));
        when(marketPriceService.currentPrice(holding)).thenReturn(new BigDecimal("90"));
        when(capitalService.maxAllowedLoss(1L)).thenReturn(new BigDecimal("100"));

        HoldingsListResponse response = service.findAll(1L);

        assertThat(response.summary().totalProfit()).isEqualByComparingTo("-100");
        assertThat(response.summary().profitRate()).isEqualByComparingTo("-10");
        assertThat(response.summary().maxAllowedLoss()).isEqualByComparingTo("100");
        assertThat(response.summary().riskUsageRate()).isEqualByComparingTo("1");
    }

    @Test
    void costExposureAggregatesSameStockAndUsesConfiguredCapital() {
        Holding first = holding();
        Holding second = holding();
        second.setHoldingId(8L);
        second.setQuantity(new BigDecimal("5"));
        Holding other = holding();
        other.setHoldingId(9L);
        other.setStockCode("000660");
        other.setQuantity(new BigDecimal("15"));
        when(holdingMapper.findActiveByUserId(1L)).thenReturn(List.of(first, second, other));
        when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            new BigDecimal("5000"), new BigDecimal("500"), new BigDecimal("1000"),
            new BigDecimal("0.02")
        ));

        PortfolioCostExposure exposure = service.costExposure(1L, "005930", "KOSPI").orElseThrow();

        assertThat(exposure.portfolioWeightRate()).isEqualByComparingTo("50");
        assertThat(exposure.capitalWeightRate()).isEqualByComparingTo("30");
        assertThat(exposure.maxCapitalWeightRate()).isEqualByComparingTo("20");
    }

    @Test
    void costExposureWithoutConfiguredCapitalDoesNotInventCapitalWeight() {
        when(holdingMapper.findActiveByUserId(1L)).thenReturn(List.of(holding()));
        when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, new BigDecimal("0.02")
        ));

        PortfolioCostExposure exposure = service.costExposure(1L, "005930", "KOSPI").orElseThrow();

        assertThat(exposure.portfolioWeightRate()).isEqualByComparingTo("100");
        assertThat(exposure.capitalWeightRate()).isNull();
        assertThat(exposure.maxCapitalWeightRate()).isNull();
    }

    @Test
    void costExposureKeepsSmallAmountAboveLargeCapitalLimit() {
        Holding holding = holding();
        holding.setBuyPrice(new BigDecimal("2000000.01"));
        holding.setQuantity(BigDecimal.ONE);
        when(holdingMapper.findActiveByUserId(1L)).thenReturn(List.of(holding));
        when(capitalService.findByUserId(1L)).thenReturn(new CapitalResponse(
            new BigDecimal("10000000"), new BigDecimal("1000000"),
            new BigDecimal("2000000"), new BigDecimal("0.02")
        ));

        PortfolioCostExposure exposure = service.costExposure(1L, "005930", "KOSPI").orElseThrow();

        assertThat(exposure.capitalWeightRate()).isGreaterThan(exposure.maxCapitalWeightRate());
    }

    private Holding holding() {
        Holding holding = new Holding();
        holding.setHoldingId(7L);
        holding.setUserId(1L);
        holding.setStockCode("005930");
        holding.setStockName("삼성전자");
        holding.setMarket("KOSPI");
        holding.setBuyPrice(new BigDecimal("100"));
        holding.setQuantity(new BigDecimal("10"));
        holding.setBuyDate(LocalDate.of(2026, 9, 1));
        holding.setStopLossRate(new BigDecimal("-5"));
        holding.setTakeProfitRate(new BigDecimal("10"));
        holding.setStatus("HOLDING");
        return holding;
    }
}
