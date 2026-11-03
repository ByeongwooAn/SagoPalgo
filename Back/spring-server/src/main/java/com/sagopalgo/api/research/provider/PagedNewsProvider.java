package com.sagopalgo.api.research.provider;
import com.sagopalgo.api.research.model.*;
public interface PagedNewsProvider extends NewsProvider {
    ResearchBatch<NewsArticle> searchBatch(ResearchRequest request);
}
