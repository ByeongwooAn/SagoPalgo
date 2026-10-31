package com.sagopalgo.api.watchlist.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.verify;
import static org.mockito.ArgumentMatchers.any;

import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.model.StockQuote;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.watchlist.dto.WatchlistResponse;
import com.sagopalgo.api.watchlist.dto.WatchlistCreateRequest;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import com.sagopalgo.api.watchlist.model.WatchlistItem;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class WatchlistServiceTest {

    @Mock
    private WatchlistMapper watchlistMapper;

    @Mock
    private MarketPriceService marketPriceService;

    @Test
    @DisplayName("관심 종목 등록은 현재가 Provider 호출 없이 저장한다")
    void registrationDoesNotDependOnMarketPrice() {
        when(watchlistMapper.insert(any(WatchlistItem.class))).thenAnswer(invocation -> {
            WatchlistItem item = invocation.getArgument(0);
            item.setWatchlistId(7L);
            return 1;
        });
        var response = new WatchlistService(watchlistMapper, marketPriceService).create(1L,
            new WatchlistCreateRequest("000660", "SK하이닉스", "KOSPI", false));
        assertThat(response.watchlistId()).isEqualTo(7L);
        verify(watchlistMapper).insert(any(WatchlistItem.class));
        verifyNoInteractions(marketPriceService);
    }

    @Test
    @DisplayName("관심 종목 목록에 현재가 Provider와 등락률을 포함한다")
    void includesMarketQuoteInWatchlist() {
        WatchlistItem item = new WatchlistItem();
        item.setWatchlistId(3L);
        item.setUserId(1L);
        item.setStockCode("005930");
        item.setStockName("삼성전자");
        item.setMarket("KOSPI");
        item.setAlertEnabled(true);
        item.setCreatedAt(LocalDateTime.of(2026, 9, 23, 1, 0));
        when(watchlistMapper.findAllByUserId(1L)).thenReturn(List.of(item));
        when(marketPriceService.quoteMarket(new MarketDataRequest("005930", "KOSPI")))
            .thenReturn(new StockQuote(
                "KB", "005930", "삼성전자", "KOSPI",
                new BigDecimal("75200"), new BigDecimal("900"), new BigDecimal("1.21"),
                BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO, BigDecimal.ZERO,
                BigDecimal.ZERO, Instant.now()
            ));

        List<WatchlistResponse> response = new WatchlistService(
            watchlistMapper,
            marketPriceService
        ).findAll(1L);

        assertThat(response).singleElement().satisfies(result -> {
            assertThat(result.provider()).isEqualTo("KB");
            assertThat(result.currentPrice()).isEqualByComparingTo("75200");
            assertThat(result.changeRate()).isEqualByComparingTo("1.21");
        });
    }

    @Test
    void deleteUsesUserScopedIdWithoutCallingPrices() {
        when(watchlistMapper.deleteByIdAndUserId(7L, 1L)).thenReturn(1);
        new WatchlistService(watchlistMapper, marketPriceService).delete(1L, 7L);
        verify(watchlistMapper).deleteByIdAndUserId(7L, 1L);
        verifyNoInteractions(marketPriceService);
    }

    @Test
    void deleteOfMissingOrOtherUsersItemIsRejected() {
        assertThatThrownBy(() -> new WatchlistService(watchlistMapper, marketPriceService).delete(2L, 7L))
            .isInstanceOf(ApiException.class).extracting("errorCode").isEqualTo(ErrorCode.RESOURCE_NOT_FOUND);
        verify(watchlistMapper).deleteByIdAndUserId(7L, 2L);
        verifyNoInteractions(marketPriceService);
    }
}
