package com.sagopalgo.api.research.dto;

import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import java.time.LocalDate;
import java.util.List;

/**
 * 종목별 뉴스와 공시를 함께 내려주는 읽기 전용 응답입니다.
 */
public record ResearchFeedResponse(
    String stockCode,
    String stockName,
    LocalDate fromDate,
    LocalDate toDate,
    List<NewsArticle> news,
    List<Disclosure> disclosures,
    List<ResearchProviderStatusResponse> providers
) {
}
