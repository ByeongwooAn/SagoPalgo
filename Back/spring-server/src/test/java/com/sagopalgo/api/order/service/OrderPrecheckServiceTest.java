package com.sagopalgo.api.order.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;

import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.config.SecuritiesProviderProperties.Provider;
import com.sagopalgo.api.kb.dto.KbBalanceItemResponse;
import com.sagopalgo.api.kb.dto.KbBalanceResponse;
import com.sagopalgo.api.kb.dto.KbBalanceSummaryResponse;
import com.sagopalgo.api.kb.service.KbAccountService;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.order.dto.OrderPrecheckRequest;
import com.sagopalgo.api.order.dto.OrderPrecheckResponse;
import com.sagopalgo.api.order.mapper.OrderPrecheckMapper;
import com.sagopalgo.api.order.model.OrderPrecheckRecord;
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class OrderPrecheckServiceTest {

    @Mock
    private OrderPrecheckMapper mapper;

    @Mock
    private KbAccountService kbAccountService;

    @Mock
    private MarketPriceService marketPriceService;

    private SecuritiesProviderProperties properties;

    @BeforeEach
    void setUp() {
        properties = new SecuritiesProviderProperties();
        properties.getKb().setAccountEnabled(true);
        properties.getKb().setOrderEnabled(true);
        properties.getKb().setMaxOrderAmount(new BigDecimal("2000"));
        properties.getKb().setMaxPriceDeviationRate(new BigDecimal("5"));
        when(mapper.insert(any())).thenAnswer(invocation -> {
            OrderPrecheckRecord record = invocation.getArgument(0);
            record.setOrderPrecheckId(31L);
            return 1;
        });
    }

    @Test
    @DisplayName("매수 주문안이 모든 안전 조건을 통과해도 실제 주문은 전송할 수 없다")
    void buyPrecheckPassesWithoutSubmission() {
        when(marketPriceService.quoteMarket(new MarketDataRequest("005930", "KOSPI")))
            .thenReturn(quote("KB", "100"));
        when(kbAccountService.settlementBalance()).thenReturn(balance("2000", List.of()));

        OrderPrecheckResponse response = service().precheck(
            1L,
            request("BUY", "103", "10")
        );

        assertThat(response.orderPrecheckId()).isEqualTo(31L);
        assertThat(response.estimatedAmount()).isEqualByComparingTo("1030");
        assertThat(response.priceDeviationRate()).isEqualByComparingTo("3");
        assertThat(response.orderAvailableCash()).isEqualByComparingTo("2000");
        assertThat(response.eligible()).isTrue();
        assertThat(response.canSubmit()).isFalse();
        assertThat(response.checks()).allMatch(check -> check.passed());
    }

    @Test
    @DisplayName("주문 스위치가 꺼져 있으면 다른 검사가 통과해도 주문 적격이 아니다")
    void disabledOrderSwitchBlocksEligibility() {
        properties.getKb().setOrderEnabled(false);
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "100"));
        when(kbAccountService.settlementBalance()).thenReturn(balance("2000", List.of()));

        OrderPrecheckResponse response = service().precheck(1L, request("BUY", "100", "10"));

        assertThat(response.eligible()).isFalse();
        assertThat(response.checks())
            .filteredOn(check -> check.code().equals("ORDER_SWITCH"))
            .singleElement()
            .satisfies(check -> assertThat(check.passed()).isFalse());
    }

    @Test
    @DisplayName("KB 주문가능수량보다 많은 매도 주문안은 차단한다")
    void sellQuantityAboveOrderableQuantityIsBlocked() {
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("KB", "100"));
        when(kbAccountService.executionBalance()).thenReturn(balance("0", List.of(balanceItem("A005930", "3"))));

        OrderPrecheckResponse response = service().precheck(1L, request("SELL", "100", "4"));

        assertThat(response.orderableQuantity()).isEqualByComparingTo("3");
        assertThat(response.eligible()).isFalse();
        assertThat(response.checks())
            .filteredOn(check -> check.code().equals("SELLABLE_QUANTITY"))
            .singleElement()
            .satisfies(check -> assertThat(check.message()).contains("부족"));
    }

    @Test
    @DisplayName("FALLBACK 현재가와 1회 주문 한도 초과를 함께 기록한다")
    void fallbackQuoteAndAmountLimitAreBlocked() {
        when(marketPriceService.quoteMarket(any())).thenReturn(quote("FALLBACK", "0"));
        when(kbAccountService.settlementBalance()).thenReturn(balance("10000", List.of()));

        OrderPrecheckResponse response = service().precheck(1L, request("BUY", "500", "5"));

        assertThat(response.eligible()).isFalse();
        assertThat(response.checks())
            .filteredOn(check -> !check.passed())
            .extracting("code")
            .contains("MAX_ORDER_AMOUNT", "REAL_PRICE", "PRICE_DEVIATION");
    }

    private OrderPrecheckService service() {
        return new OrderPrecheckService(mapper, kbAccountService, marketPriceService, properties);
    }

    private OrderPrecheckRequest request(String side, String price, String quantity) {
        return new OrderPrecheckRequest(
            "005930",
            "삼성전자",
            "KOSPI",
            side,
            new BigDecimal(price),
            new BigDecimal(quantity)
        );
    }

    private StockQuote quote(String provider, String currentPrice) {
        return new StockQuote(
            provider,
            "005930",
            "삼성전자",
            "KOSPI",
            new BigDecimal(currentPrice),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            Instant.now()
        );
    }

    private KbBalanceResponse balance(String orderAvailableCash, List<KbBalanceItemResponse> items) {
        return new KbBalanceResponse(
            new KbBalanceSummaryResponse(
                "SETTLEMENT",
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                new BigDecimal(orderAvailableCash),
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                BigDecimal.ZERO,
                Integer.toString(items.size())
            ),
            items
        );
    }

    private KbBalanceItemResponse balanceItem(String stockCode, String orderableQuantity) {
        return new KbBalanceItemResponse(
            "주식",
            "",
            "KRW",
            stockCode,
            "삼성전자",
            new BigDecimal("10"),
            new BigDecimal(orderableQuantity),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            new BigDecimal("100"),
            new BigDecimal("90"),
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            BigDecimal.ZERO,
            "",
            "KRX"
        );
    }
}
