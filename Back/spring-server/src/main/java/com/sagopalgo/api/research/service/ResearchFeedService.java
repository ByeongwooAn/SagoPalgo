package com.sagopalgo.api.research.service;

import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.dto.ResearchFeedResponse;
import com.sagopalgo.api.research.dto.ResearchProviderStatusResponse;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import com.sagopalgo.api.research.provider.DisclosureProvider;
import com.sagopalgo.api.research.provider.NewsProvider;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.util.StringUtils;

/**
 * 한 종목의 뉴스와 공시를 독립 Provider에서 모아 부분 성공이 가능한 응답으로 조합합니다.
 */
@Service
public class ResearchFeedService {

    private static final Logger log = LoggerFactory.getLogger(ResearchFeedService.class);

    private final List<NewsProvider> newsProviders;
    private final List<DisclosureProvider> disclosureProviders;
    private final ResearchProviderProperties properties;
    private final ResearchFeedStore researchFeedStore;

    public ResearchFeedService(
        List<NewsProvider> newsProviders,
        List<DisclosureProvider> disclosureProviders,
        ResearchProviderProperties properties,
        ResearchFeedStore researchFeedStore
    ) {
        this.newsProviders = newsProviders;
        this.disclosureProviders = disclosureProviders;
        this.properties = properties;
        this.researchFeedStore = researchFeedStore;
    }

    public ResearchFeedResponse getStoredFeed(
        String stockCode,
        String stockName,
        LocalDate fromDate,
        LocalDate toDate
    ) {
        ResearchRequest request = request(stockCode, stockName, fromDate, toDate);
        StoredResearchFeed stored = researchFeedStore.find(request);
        List<ResearchProviderStatusResponse> statuses = List.of(status(
            "LOCAL_DB",
            "CACHE",
            "SUCCESS",
            "뉴스 %d건 · 공시 %d건".formatted(stored.news().size(), stored.disclosures().size())
        ));
        return response(request, stored, statuses);
    }

    public ResearchFeedResponse syncFeed(
        String stockCode,
        String stockName,
        LocalDate fromDate,
        LocalDate toDate
    ) {
        ResearchRequest request = request(stockCode, stockName, fromDate, toDate);
        List<ResearchProviderStatusResponse> statuses = new ArrayList<>();
        List<NewsArticle> news = collectNews(request, statuses);
        List<Disclosure> disclosures = collectDisclosures(request, statuses);
        StoredResearchFeed stored = researchFeedStore.saveAndFind(request, news, disclosures);
        return response(request, stored, statuses);
    }

    private ResearchRequest request(String stockCode, String stockName, LocalDate fromDate, LocalDate toDate) {
        validate(stockCode, stockName);
        LocalDate normalizedToDate = toDate == null ? LocalDate.now(java.time.ZoneId.of("Asia/Seoul")) : toDate;
        LocalDate normalizedFromDate = fromDate == null
            ? normalizedToDate.minusDays(Math.max(1, properties.getOpenDart().getDefaultLookbackDays()))
            : fromDate;
        if (normalizedFromDate.isAfter(normalizedToDate)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "조회 시작일은 종료일보다 늦을 수 없습니다.");
        }

        return new ResearchRequest(
            stockCode.trim(),
            stockName.trim(),
            normalizedFromDate,
            normalizedToDate
        );
    }

    private ResearchFeedResponse response(
        ResearchRequest request,
        StoredResearchFeed stored,
        List<ResearchProviderStatusResponse> statuses
    ) {
        return new ResearchFeedResponse(
            request.stockCode(),
            request.stockName(),
            request.fromDate(),
            request.toDate(),
            stored.news(),
            stored.disclosures(),
            List.copyOf(statuses)
        );
    }

    private List<NewsArticle> collectNews(
        ResearchRequest request,
        List<ResearchProviderStatusResponse> statuses
    ) {
        List<NewsArticle> result = new ArrayList<>();
        for (NewsProvider provider : newsProviders) {
            if (!provider.supports(request)) {
                statuses.add(status(provider.providerCode(), "NEWS", "DISABLED", "비활성 또는 설정 전"));
                continue;
            }
            try {
                List<NewsArticle> articles = provider.search(request);
                result.addAll(articles);
                statuses.add(status(provider.providerCode(), "NEWS", "SUCCESS", articles.size() + "건 조회"));
            } catch (ApiException exception) {
                log.warn("뉴스 Provider 조회 실패. provider={} message={}", provider.providerCode(), exception.getMessage());
                statuses.add(status(provider.providerCode(), "NEWS", "FAILED", exception.getMessage()));
            }
        }
        return List.copyOf(result);
    }

    private List<Disclosure> collectDisclosures(
        ResearchRequest request,
        List<ResearchProviderStatusResponse> statuses
    ) {
        List<Disclosure> result = new ArrayList<>();
        for (DisclosureProvider provider : disclosureProviders) {
            if (!provider.supports(request)) {
                statuses.add(status(provider.providerCode(), "DISCLOSURE", "DISABLED", "비활성 또는 설정 전"));
                continue;
            }
            try {
                List<Disclosure> items = provider.search(request);
                result.addAll(items);
                statuses.add(status(provider.providerCode(), "DISCLOSURE", "SUCCESS", items.size() + "건 조회"));
            } catch (ApiException exception) {
                log.warn("공시 Provider 조회 실패. provider={} message={}", provider.providerCode(), exception.getMessage());
                statuses.add(status(provider.providerCode(), "DISCLOSURE", "FAILED", exception.getMessage()));
            }
        }
        return List.copyOf(result);
    }

    private ResearchProviderStatusResponse status(String provider, String dataType, String status, String message) {
        return new ResearchProviderStatusResponse(provider, dataType, status, message);
    }

    private void validate(String stockCode, String stockName) {
        if (!StringUtils.hasText(stockCode)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "종목코드가 필요합니다.");
        }
        if (!StringUtils.hasText(stockName)) {
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "종목명이 필요합니다.");
        }
    }
}
