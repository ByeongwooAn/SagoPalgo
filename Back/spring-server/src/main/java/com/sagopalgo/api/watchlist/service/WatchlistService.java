package com.sagopalgo.api.watchlist.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.market.model.MarketDataRequest;
import com.sagopalgo.api.market.service.MarketPriceService;
import com.sagopalgo.api.watchlist.dto.WatchlistAlertUpdateRequest;
import com.sagopalgo.api.watchlist.dto.WatchlistCreateRequest;
import com.sagopalgo.api.watchlist.dto.WatchlistCreateResponse;
import com.sagopalgo.api.watchlist.dto.WatchlistResponse;
import com.sagopalgo.api.watchlist.mapper.WatchlistMapper;
import com.sagopalgo.api.watchlist.model.WatchlistItem;
import java.util.List;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 관심 종목 등록, 목록 조회, 알림 설정 변경을 담당하는 서비스입니다.
 */
@Service
public class WatchlistService {

    private final WatchlistMapper watchlistMapper;
    private final MarketPriceService marketPriceService;

    public WatchlistService(
        WatchlistMapper watchlistMapper,
        MarketPriceService marketPriceService
    ) {
        this.watchlistMapper = watchlistMapper;
        this.marketPriceService = marketPriceService;
    }

    @Transactional(readOnly = true)
    public List<WatchlistResponse> findAll(Long userId) {
        return watchlistMapper.findAllByUserId(userId)
            .stream()
            .map(this::toResponse)
            .toList();
    }

    private WatchlistResponse toResponse(WatchlistItem item) {
        return WatchlistResponse.from(
            item,
            marketPriceService.quoteMarket(new MarketDataRequest(item.getStockCode(), item.getMarket()))
        );
    }

    @Transactional
    public WatchlistCreateResponse create(Long userId, WatchlistCreateRequest request) {
        if (watchlistMapper.existsByUserStockAndMarket(userId, request.stockCode(), request.market())) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "이미 등록된 관심 종목입니다.");
        }

        WatchlistItem item = new WatchlistItem();
        item.setUserId(userId);
        item.setStockCode(request.stockCode());
        item.setStockName(request.stockName());
        item.setMarket(request.market());
        item.setAlertEnabled(request.alertEnabled());

        try {
            watchlistMapper.insert(item);
        } catch (DuplicateKeyException exception) {
            throw new ApiException(ErrorCode.DUPLICATE_RESOURCE, "이미 등록된 관심 종목입니다.");
        }

        return new WatchlistCreateResponse(item.getWatchlistId());
    }

    @Transactional
    public WatchlistResponse updateAlert(Long userId, Long watchlistId, WatchlistAlertUpdateRequest request) {
        int updatedRows = watchlistMapper.updateAlertEnabled(watchlistId, userId, request.alertEnabled());
        if (updatedRows == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "관심 종목을 찾을 수 없습니다.");
        }

        return watchlistMapper.findByIdAndUserId(watchlistId, userId)
            .map(this::toResponse)
            .orElseThrow(() -> new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "관심 종목을 찾을 수 없습니다."));
    }

    @Transactional
    public void delete(Long userId, Long watchlistId) {
        int deletedRows = watchlistMapper.deleteByIdAndUserId(watchlistId, userId);
        if (deletedRows == 0) {
            throw new ApiException(ErrorCode.RESOURCE_NOT_FOUND, "관심 종목을 찾을 수 없습니다.");
        }
    }
}
