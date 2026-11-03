package com.sagopalgo.api.research.provider;
import com.sagopalgo.api.research.model.*;
public interface PagedDisclosureProvider extends DisclosureProvider {
    ResearchBatch<Disclosure> searchBatch(ResearchRequest request);
}
