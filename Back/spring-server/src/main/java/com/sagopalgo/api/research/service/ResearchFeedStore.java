package com.sagopalgo.api.research.service;

import com.sagopalgo.api.research.mapper.ResearchDisclosureMapper;
import com.sagopalgo.api.research.mapper.ResearchNewsMapper;
import com.sagopalgo.api.research.model.Disclosure;
import com.sagopalgo.api.research.model.NewsArticle;
import com.sagopalgo.api.research.model.ResearchDisclosureRecord;
import com.sagopalgo.api.research.model.ResearchNewsRecord;
import com.sagopalgo.api.research.model.ResearchRequest;
import com.sagopalgo.api.research.model.StoredResearchFeed;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * 외부 Provider 결과를 로컬 DB에 중복 없이 저장하고 다시 조회합니다.
 */
@Service
public class ResearchFeedStore {

    private static final int PROVIDER_MAX_LENGTH = 30;
    private static final int STOCK_CODE_MAX_LENGTH = 30;
    private static final int STOCK_NAME_MAX_LENGTH = 100;
    private static final int TITLE_MAX_LENGTH = 500;
    private static final int LINK_MAX_LENGTH = 1000;
    private static final int CORP_CODE_MAX_LENGTH = 20;
    private static final int CORP_NAME_MAX_LENGTH = 100;
    private static final int REPORT_NAME_MAX_LENGTH = 500;
    private static final int RECEIPT_NUMBER_MAX_LENGTH = 30;
    private static final int SUBMITTER_NAME_MAX_LENGTH = 100;

    private final ResearchNewsMapper newsMapper;
    private final ResearchDisclosureMapper disclosureMapper;

    public ResearchFeedStore(ResearchNewsMapper newsMapper, ResearchDisclosureMapper disclosureMapper) {
        this.newsMapper = newsMapper;
        this.disclosureMapper = disclosureMapper;
    }

    @Transactional
    public StoredResearchFeed saveAndFind(
        ResearchRequest request,
        List<NewsArticle> news,
        List<Disclosure> disclosures
    ) {
        news.stream()
            .filter(this::isPersistable)
            .map(article -> toRecord(request, article))
            .forEach(newsMapper::upsert);
        disclosures.stream()
            .filter(this::isPersistable)
            .map(this::toRecord)
            .forEach(disclosureMapper::upsert);
        return findInternal(request);
    }

    @Transactional(readOnly = true)
    public StoredResearchFeed find(ResearchRequest request) {
        return findInternal(request);
    }

    private StoredResearchFeed findInternal(ResearchRequest request) {
        List<NewsArticle> news = newsMapper.findByStockCodeAndDateRange(
                request.stockCode(),
                request.fromDate(),
                request.toDate()
            )
            .stream()
            .map(this::toArticle)
            .toList();
        List<Disclosure> disclosures = disclosureMapper.findByStockCodeAndDateRange(
                request.stockCode(),
                request.fromDate(),
                request.toDate()
            )
            .stream()
            .map(this::toDisclosure)
            .toList();
        return new StoredResearchFeed(news, disclosures);
    }

    private ResearchNewsRecord toRecord(ResearchRequest request, NewsArticle article) {
        ResearchNewsRecord record = new ResearchNewsRecord();
        record.setProvider(limit(article.provider(), PROVIDER_MAX_LENGTH));
        record.setContentKey(contentKey(request.stockCode(), article));
        record.setStockCode(limit(request.stockCode(), STOCK_CODE_MAX_LENGTH));
        record.setStockName(limit(request.stockName(), STOCK_NAME_MAX_LENGTH));
        record.setTitle(limit(article.title(), TITLE_MAX_LENGTH));
        record.setLink(limit(article.link(), LINK_MAX_LENGTH));
        record.setSummary(article.summary());
        record.setPublishedAt(article.publishedAt());
        return record;
    }

    private ResearchDisclosureRecord toRecord(Disclosure disclosure) {
        ResearchDisclosureRecord record = new ResearchDisclosureRecord();
        record.setProvider(limit(disclosure.provider(), PROVIDER_MAX_LENGTH));
        record.setStockCode(limit(disclosure.stockCode(), STOCK_CODE_MAX_LENGTH));
        record.setCorpCode(limit(disclosure.corpCode(), CORP_CODE_MAX_LENGTH));
        record.setCorpName(limit(disclosure.corpName(), CORP_NAME_MAX_LENGTH));
        record.setReportName(limit(disclosure.reportName(), REPORT_NAME_MAX_LENGTH));
        record.setReceiptNumber(limit(disclosure.receiptNumber(), RECEIPT_NUMBER_MAX_LENGTH));
        record.setSubmitterName(limit(disclosure.submitterName(), SUBMITTER_NAME_MAX_LENGTH));
        record.setReceiptDate(disclosure.receiptDate());
        record.setLink(limit(disclosure.link(), LINK_MAX_LENGTH));
        return record;
    }

    private NewsArticle toArticle(ResearchNewsRecord record) {
        return new NewsArticle(
            record.getProvider(),
            record.getStockCode(),
            record.getTitle(),
            record.getLink(),
            record.getSummary(),
            record.getPublishedAt()
        );
    }

    private Disclosure toDisclosure(ResearchDisclosureRecord record) {
        return new Disclosure(
            record.getProvider(),
            record.getStockCode(),
            record.getCorpCode(),
            record.getCorpName(),
            record.getReportName(),
            record.getReceiptNumber(),
            record.getSubmitterName(),
            record.getReceiptDate(),
            record.getLink()
        );
    }

    private String contentKey(String stockCode, NewsArticle article) {
        String identity = article.provider() + "|" + stockCode + "|" + article.link();
        if (article.link() == null || article.link().isBlank()) {
            identity = article.provider() + "|" + stockCode + "|" + article.title() + "|" + article.publishedAt();
        }
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(identity.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 알고리즘을 사용할 수 없습니다.", exception);
        }
    }

    private boolean isPersistable(NewsArticle article) {
        return article != null
            && (!isBlank(article.link()) || !isBlank(article.title()));
    }

    private boolean isPersistable(Disclosure disclosure) {
        return disclosure != null && !isBlank(disclosure.receiptNumber());
    }

    private boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private String limit(String value, int maxLength) {
        if (value == null) {
            return "";
        }
        String trimmed = value.trim();
        return trimmed.length() <= maxLength ? trimmed : trimmed.substring(0, maxLength);
    }
}
