package com.sagopalgo.api.research.model;

import java.util.List;

/**
 * 로컬 DB에서 조회한 종목별 뉴스와 공시 묶음입니다.
 */
public record StoredResearchFeed(
    List<NewsArticle> news,
    List<Disclosure> disclosures
) {
}
