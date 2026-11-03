package com.sagopalgo.api.research.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.provider.DisclosureProvider;
import java.net.URI;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * OpenDART 공시검색 결과를 종목별 내부 공시 모델로 정규화합니다.
 */
@Component
@Order(10)
public class OpenDartDisclosureProvider implements com.sagopalgo.api.research.provider.PagedDisclosureProvider {

    private static final String PROVIDER_CODE = "OPEN_DART";
    private static final String SUCCESS_STATUS = "000";
    private static final String NO_DATA_STATUS = "013";
    private static final DateTimeFormatter DART_DATE = DateTimeFormatter.BASIC_ISO_DATE;

    private final ResearchProviderProperties.OpenDart properties;
    private final OpenDartCorpCodeResolver corpCodeResolver;
    private final RestClient restClient;
    private final ResearchProviderProperties.Incremental incremental;

    public OpenDartDisclosureProvider(
        ResearchProviderProperties properties,
        OpenDartCorpCodeResolver corpCodeResolver,
        RestClient restClient
    ) {
        this.properties = properties.getOpenDart();
        this.corpCodeResolver = corpCodeResolver;
        this.restClient = restClient;
        incremental=properties.getIncremental();
    }

    @Override
    public String providerCode() {
        return PROVIDER_CODE;
    }

    @Override
    public boolean supports(ResearchRequest request) {
        return properties.isEnabled()
            && request != null
            && StringUtils.hasText(request.stockCode());
    }

    @Override
    public List<Disclosure> search(ResearchRequest request) {
        return searchBatch(request).items();
    }

    @Override
    public com.sagopalgo.api.research.model.ResearchBatch<Disclosure> searchBatch(ResearchRequest request) {
        ensureConfigured();
        OpenDartCorpCodeResolver.CorpCode corpCode = corpCodeResolver.resolve(request.stockCode());
        List<Disclosure> all=new ArrayList<>();
        int max=incremental.isEnabled()?incremental.getMaxPages():1,pages=0;
        int firstTotal=-1;
        boolean datesKnown=true;
        java.util.Set<String> seenPages=new java.util.HashSet<>();
        java.util.Map<String,Disclosure> seenReceipts=new java.util.HashMap<>();
        for(int page=1;page<=max;page++) {
        JsonNode response;
        try {
            response = restClient.get()
                .uri(disclosureUri(corpCode.value(), request,page))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientException exception) {
            if(pages>0) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"LOOKUP_FAILED");
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 공시검색 API 호출에 실패했습니다.");
        }

        String status = response == null ? "" : response.path("status").asText("");
        if (NO_DATA_STATUS.equals(status)) {
            return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages+1,page==1,page==1?null:"MISSING_PAGE");
        }
        if (!SUCCESS_STATUS.equals(status)) {
            if(pages>0) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"LOOKUP_FAILED");
            String message = response == null ? "" : response.path("message").asText("");
            throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                StringUtils.hasText(message) ? "OpenDART 공시검색 실패: " + message : "OpenDART 공시검색에 실패했습니다."
            );
        }

        JsonNode items = response.path("list");
        if (!items.isArray()) {
            if(pages>0) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"INVALID_PAGE");
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 공시검색 응답 형식이 올바르지 않습니다.");
        }
        pages++;
        if(!seenPages.add(com.sagopalgo.api.common.util.ContentHash.sha256(items.toString())))
            return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"REPEATED_PAGE");
        List<Disclosure> disclosures = new ArrayList<>();
        for (JsonNode item : items) {
            String receiptNumber = item.path("rcept_no").asText("");
            if(!receiptNumber.matches("[0-9]{14}") || parseDate(item.path("rcept_dt").asText(""))==null) datesKnown=false;
            disclosures.add(new Disclosure(
                PROVIDER_CODE,
                request.stockCode(),
                corpCode.value(),
                textOrFallback(item, "corp_name", corpCode.corpName()),
                item.path("report_nm").asText(""),
                receiptNumber,
                item.path("flr_nm").asText(""),
                parseDate(item.path("rcept_dt").asText("")),
                disclosureLink(receiptNumber)
            ));
        }
        for(var value:disclosures) {
            var old=seenReceipts.putIfAbsent(value.receiptNumber(),value);
            if(old==null) all.add(value);else if(!old.equals(value)) datesKnown=false;
        }
        var total=response.path("total_page");
        if(!total.isIntegralNumber() || !total.canConvertToInt() || total.asInt()<1 ||
            (response.has("page_no") && response.path("page_no").asInt(-1)!=page))
            return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"PAGE_METADATA_UNCONFIRMED");
        if(firstTotal<0) firstTotal=total.asInt();
        else if(firstTotal!=total.asInt()) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"RANGE_CHANGED");
        if(page>=firstTotal) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,datesKnown,datesKnown?null:"DATE_UNCONFIRMED");
        if(items.isEmpty()) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"MISSING_PAGE");
        }
        return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"PAGE_LIMIT");
    }

    private URI disclosureUri(String corpCode, ResearchRequest request,int page) {
        return UriComponentsBuilder
            .fromUriString(endpoint(properties.getDisclosurePath()))
            .queryParam("crtfc_key", properties.getApiKey())
            .queryParam("corp_code", corpCode)
            .queryParam("bgn_de", request.fromDate().format(DART_DATE))
            .queryParam("end_de", request.toDate().format(DART_DATE))
            .queryParam("page_no", page)
            .queryParam("page_count", Math.max(1, Math.min(properties.getPageCount(), 100)))
            .build()
            .encode()
            .toUri();
    }

    private String disclosureLink(String receiptNumber) {
        if (!StringUtils.hasText(receiptNumber)) {
            return "";
        }
        return "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=" + receiptNumber;
    }

    private LocalDate parseDate(String value) {
        try {
            return LocalDate.parse(value, DART_DATE);
        } catch (DateTimeParseException exception) {
            return null;
        }
    }

    private String textOrFallback(JsonNode item, String fieldName, String fallback) {
        String value = item.path(fieldName).asText("");
        return StringUtils.hasText(value) ? value : fallback;
    }

    private String endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath;
    }

    private void ensureConfigured() {
        if (!StringUtils.hasText(properties.getBaseUrl())
            || !StringUtils.hasText(properties.getDisclosurePath())
            || !StringUtils.hasText(properties.getCorpCodePath())
            || !StringUtils.hasText(properties.getApiKey())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART API 설정이 필요합니다.");
        }
    }
}
