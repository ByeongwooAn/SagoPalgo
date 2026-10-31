package com.sagopalgo.api.research.client;

import com.fasterxml.jackson.databind.JsonNode;
import com.sagopalgo.api.common.exception.ApiException;
import com.sagopalgo.api.common.exception.ErrorCode;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.provider.NewsProvider;
import java.net.URI;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
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
import org.springframework.web.util.HtmlUtils;
import org.springframework.web.util.UriComponentsBuilder;

/**
 * NAVER API HUB의 뉴스 검색 결과를 내부 뉴스 모델로 정규화합니다.
 */
@Component
@Order(10)
public class NaverNewsProvider implements NewsProvider {

    private static final String PROVIDER_CODE = "NAVER_NEWS";
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private final ResearchProviderProperties.NaverNews properties;
    private final RestClient restClient;

    public NaverNewsProvider(ResearchProviderProperties properties, RestClient restClient) {
        this.properties = properties.getNaverNews();
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
            && StringUtils.hasText(request.stockCode())
            && StringUtils.hasText(request.stockName());
    }

    @Override
    public List<NewsArticle> search(ResearchRequest request) {
        ensureConfigured();

        JsonNode response;
        try {
            response = restClient.get()
                .uri(searchUri(request.stockName()))
                .accept(MediaType.APPLICATION_JSON)
                .header("X-NCP-APIGW-API-KEY-ID", properties.getClientId())
                .header("X-NCP-APIGW-API-KEY", properties.getClientSecret())
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientException exception) {
            throw NaverNewsErrors.requestFailure(exception);
        }

        JsonNode items = response == null ? null : response.path("items");
        if (items == null || !items.isArray()) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "네이버 뉴스 검색 응답 형식이 올바르지 않습니다.");
        }

        List<NewsArticle> articles = new ArrayList<>();
        for (JsonNode item : items) {
            Instant publishedAt = parsePublishedAt(item.path("pubDate").asText(""));
            if (!isWithinRange(publishedAt, request)) {
                continue;
            }
            String originalLink = item.path("originallink").asText("");
            articles.add(new NewsArticle(
                PROVIDER_CODE,
                request.stockCode(),
                plainText(item.path("title").asText("")),
                StringUtils.hasText(originalLink) ? originalLink : item.path("link").asText(""),
                plainText(item.path("description").asText("")),
                publishedAt
            ));
        }
        return List.copyOf(articles);
    }

    private URI searchUri(String stockName) {
        return UriComponentsBuilder
            .fromUriString(endpoint(properties.getSearchPath()))
            .queryParam("query", stockName)
            .queryParam("display", Math.max(1, Math.min(properties.getDisplay(), 100)))
            .queryParam("start", 1)
            .queryParam("sort", "date")
            .queryParam("format", "json")
            .build()
            .encode()
            .toUri();
    }

    private String endpoint(String path) {
        String normalizedPath = StringUtils.hasText(path) && path.startsWith("/") ? path : "/" + path;
        return properties.getBaseUrl().replaceAll("/+$", "") + normalizedPath;
    }

    private Instant parsePublishedAt(String value) {
        if (!StringUtils.hasText(value)) {
            return null;
        }
        try {
            return ZonedDateTime.parse(value, DateTimeFormatter.RFC_1123_DATE_TIME).toInstant();
        } catch (DateTimeParseException exception) {
            return null;
        }
    }

    private boolean isWithinRange(Instant publishedAt, ResearchRequest request) {
        if (publishedAt == null) {
            return true;
        }
        var publishedDate = publishedAt.atZone(SEOUL).toLocalDate();
        return !publishedDate.isBefore(request.fromDate()) && !publishedDate.isAfter(request.toDate());
    }

    private String plainText(String value) {
        return HtmlUtils.htmlUnescape(value.replaceAll("<[^>]+>", "")).trim();
    }

    private void ensureConfigured() {
        if (!StringUtils.hasText(properties.getBaseUrl())
            || !StringUtils.hasText(properties.getSearchPath())
            || !StringUtils.hasText(properties.getClientId())
            || !StringUtils.hasText(properties.getClientSecret())) {
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "네이버 뉴스 검색 API 설정이 필요합니다.");
        }
    }
}
