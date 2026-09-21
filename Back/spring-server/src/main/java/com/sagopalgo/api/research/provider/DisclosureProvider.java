package com.sagopalgo.api.research.provider;

import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.ResearchRequest;
import java.util.List;

/**
 * 전자공시 공급자를 교체할 수 있게 만드는 공통 경계입니다.
 */
public interface DisclosureProvider {

    String providerCode();

    boolean supports(ResearchRequest request);

    List<Disclosure> search(ResearchRequest request);
}
