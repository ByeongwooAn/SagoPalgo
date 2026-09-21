package com.sagopalgo.api.research.model;

import java.time.Instant;

/**
 * 뉴스 검색 Provider 응답을 통일한 내부 모델입니다.
 */
public record NewsArticle(
    String provider,
    String stockCode,
    String title,
    String link,
    String summary,
    Instant publishedAt
) {
}
