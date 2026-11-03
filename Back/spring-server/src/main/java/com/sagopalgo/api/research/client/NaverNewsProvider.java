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
public class NaverNewsProvider implements com.sagopalgo.api.research.provider.PagedNewsProvider {

    private static final String PROVIDER_CODE = "NAVER_NEWS";
    private static final ZoneId SEOUL = ZoneId.of("Asia/Seoul");

    private final ResearchProviderProperties.NaverNews properties;
    private final RestClient restClient;
    private final ResearchProviderProperties.Incremental incremental;

    public NaverNewsProvider(ResearchProviderProperties properties, RestClient restClient) {
        this.properties = properties.getNaverNews();
        this.restClient = restClient;
        this.incremental=properties.getIncremental();
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
        return searchBatch(request).items();
    }

    @Override
    public com.sagopalgo.api.research.model.ResearchBatch<NewsArticle> searchBatch(ResearchRequest request) {
        ensureConfigured();
        var all=new ArrayList<NewsArticle>();
        int max=incremental.isEnabled()?incremental.getMaxPages():1;
        int display=Math.max(1,Math.min(properties.getDisplay(),100)),start=1,pages=0;
        long firstTotal=-1;
        java.util.Set<String> seenPages=new java.util.HashSet<>();
        java.util.Map<String,NewsArticle> seenArticles=new java.util.HashMap<>();
        Instant prior=null;
        boolean datesKnown=true;
        for(int page=0;page<max;page++) {
        JsonNode response;
        try {
            response = restClient.get()
                .uri(searchUri(request.stockName(),start))
                .accept(MediaType.APPLICATION_JSON)
                .header("X-NCP-APIGW-API-KEY-ID", properties.getClientId())
                .header("X-NCP-APIGW-API-KEY", properties.getClientSecret())
                .retrieve()
                .body(JsonNode.class);
        } catch (RestClientException exception) {
            if(pages>0) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"LOOKUP_FAILED");
            throw NaverNewsErrors.requestFailure(exception);
        }

        JsonNode items = response == null ? null : response.path("items");
        if (items == null || !items.isArray()) {
            if(pages>0) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"INVALID_PAGE");
            throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "네이버 뉴스 검색 응답 형식이 올바르지 않습니다.");
        }
        pages++;
        String pageHash=com.sagopalgo.api.common.util.ContentHash.sha256(items.toString());
        if(!seenPages.add(pageHash)) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"REPEATED_PAGE");
        boolean boundary=false;
        List<NewsArticle> articles = new ArrayList<>();
        for (JsonNode item : items) {
            Instant publishedAt = parsePublishedAt(item.path("pubDate").asText(""));
            if(publishedAt==null || (prior!=null && publishedAt.isAfter(prior))) datesKnown=false;
            if(publishedAt!=null) {
                prior=publishedAt;
                if(publishedAt.atZone(SEOUL).toLocalDate().isBefore(request.fromDate())) boundary=true;
            }
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
        for(var article:articles) {
            String identity=article.link()==null || article.link().isBlank()?article.title()+"|"+article.publishedAt():article.link();
            var old=seenArticles.putIfAbsent(identity,article);
            if(old==null) all.add(article);else if(!old.equals(article)) datesKnown=false;
        }
        JsonNode total=response.path("total");
        if(!total.isIntegralNumber() || !total.canConvertToLong() || total.asLong()<start-1L+items.size() || items.size()>display ||
            (response.has("start") && response.path("start").asInt(-1)!=start))
            return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"PAGE_METADATA_UNCONFIRMED");
        if(firstTotal<0) firstTotal=total.asLong();
        else if(firstTotal!=total.asLong()) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"RANGE_CHANGED");
        if(start-1L+items.size()>=firstTotal || (boundary && datesKnown))
            return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,datesKnown,datesKnown?null:"DATE_ORDER_UNCONFIRMED");
        if(items.isEmpty()) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"MISSING_PAGE");
        start+=display;
        if(start>1000) return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"SEARCH_WINDOW_LIMIT");
        }
        return new com.sagopalgo.api.research.model.ResearchBatch<>(all,pages,false,"PAGE_LIMIT");
    }

    private URI searchUri(String stockName,int start) {
        return UriComponentsBuilder
            .fromUriString(endpoint(properties.getSearchPath()))
            .queryParam("query", stockName)
            .queryParam("display", Math.max(1, Math.min(properties.getDisplay(), 100)))
            .queryParam("start", start)
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
