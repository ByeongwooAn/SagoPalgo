package com.sagopalgo.api.research.provider;

import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.util.List;

/**
 * 뉴스 검색 공급자를 교체할 수 있게 만드는 공통 경계입니다.
 */
public interface NewsProvider {

    String providerCode();

    boolean supports(ResearchRequest request);

    List<NewsArticle> search(ResearchRequest request);
}
