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
public class OpenDartDisclosureProvider implements DisclosureProvider {

    private static final String PROVIDER_CODE = "OPEN_DART";
    private static final String SUCCESS_STATUS = "000";
    private static final String NO_DATA_STATUS = "013";
    private static final DateTimeFormatter DART_DATE = DateTimeFormatter.BASIC_ISO_DATE;

    private final ResearchProviderProperties.OpenDart properties;
    private final OpenDartCorpCodeResolver corpCodeResolver;
    private final RestClient restClient;

    public OpenDartDisclosureProvider(
        ResearchProviderProperties properties,
        OpenDartCorpCodeResolver corpCodeResolver,
        RestClient restClient
    ) {
        this.properties = properties.getOpenDart();
        this.corpCodeResolver = corpCodeResolver;
        this.restClient = restClient;
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
        ensureConfigured();
        OpenDartCorpCodeResolver.CorpCode corpCode = corpCodeResolver.resolve(request.stockCode());

        JsonNode response;
        try {
            response = restClient.get()
                .uri(disclosureUri(corpCode.value(), request))
                .accept(MediaType.APPLICATION_JSON)
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientException exception) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 공시검색 API 호출에 실패했습니다.");
        }

        String status = response == null ? "" : response.path("status").asText("");
        if (NO_DATA_STATUS.equals(status)) {
            return List.of();
        }
        if (!SUCCESS_STATUS.equals(status)) {
            String message = response == null ? "" : response.path("message").asText("");
            throw new ApiException(
                ErrorCode.EXTERNAL_DATA_ERROR,
                StringUtils.hasText(message) ? "OpenDART 공시검색 실패: " + message : "OpenDART 공시검색에 실패했습니다."
            );
        }

        JsonNode items = response.path("list");
        if (!items.isArray()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "OpenDART 공시검색 응답 형식이 올바르지 않습니다.");
        }

        List<Disclosure> disclosures = new ArrayList<>();
        for (JsonNode item : items) {
            String receiptNumber = item.path("rcept_no").asText("");
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
        return List.copyOf(disclosures);
    }

    private URI disclosureUri(String corpCode, ResearchRequest request) {
        return UriComponentsBuilder
            .fromUriString(endpoint(properties.getDisclosurePath()))
            .queryParam("crtfc_key", properties.getApiKey())
            .queryParam("corp_code", corpCode)
            .queryParam("bgn_de", request.fromDate().format(DART_DATE))
            .queryParam("end_de", request.toDate().format(DART_DATE))
            .queryParam("page_no", 1)
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
