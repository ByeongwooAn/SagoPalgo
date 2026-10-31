package com.sagopalgo.api.dashboard.service;

import com.sagopalgo.api.dashboard.dto.DashboardNewsSummary;
import com.sagopalgo.api.market.client.KisMarketPriceClient;
import com.sagopalgo.api.market.model.MarketIndexSnapshot;
import com.sagopalgo.api.research.mapper.ResearchNewsMapper;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Service;

/** 조회 실패와 수집 전 상태를 구분하며 가격/뉴스를 임의로 채우지 않습니다. */
@Service
public class DashboardBriefingService {
    private static final List<String> POSITIVE = List.of("실적 개선", "흑자", "수주", "상향", "최대 실적", "배당 확대");
    private static final List<String> NEGATIVE = List.of("적자", "하향", "횡령", "소송", "상장폐지", "실적 부진", "급락");
    private final KisMarketPriceClient kis;
    private final ResearchNewsMapper newsMapper;

    public DashboardBriefingService(KisMarketPriceClient kis, ResearchNewsMapper newsMapper) {
        this.kis = kis;
        this.newsMapper = newsMapper;
    }

    public MarketIndexSnapshot index() { return kis.kospi(); }

    public DashboardNewsSummary news(Long userId) {
        Instant now = Instant.now();
        try {
            var records = newsMapper.findRecentForUser(userId, now.minus(7, ChronoUnit.DAYS), now);
            Set<String> identities = new HashSet<>();
            int positive = 0;
            int negative = 0;
            Instant latest = null;
            for (var record : records) {
                String identity = record.getProvider() + ":" + (record.getLink() == null || record.getLink().isBlank()
                    ? record.getTitle() : record.getLink());
                if (!identities.add(identity)) continue;
                String content = (record.getTitle() + " " + record.getSummary());
                boolean pos = POSITIVE.stream().anyMatch(content::contains);
                boolean neg = NEGATIVE.stream().anyMatch(content::contains);
                if (pos && !neg) positive++;
                if (neg && !pos) negative++;
                if (record.getPublishedAt() != null && (latest == null || record.getPublishedAt().isAfter(latest))) {
                    latest = record.getPublishedAt();
                }
            }
            String label = identities.isEmpty() ? "저장 뉴스 없음" : positive > negative ? "긍정 우세" : negative > positive ? "부정 우세" : "중립";
            return new DashboardNewsSummary(identities.isEmpty() ? "EMPTY" : "SUCCESS", label,
                "보유·관심 종목의 최근 7일 뉴스 최대 200행 · 중복 제거 · 키워드 분류(혼합은 중립)",
                identities.size(), positive, negative, latest);
        } catch (DataAccessException exception) {
            return new DashboardNewsSummary("FAILED", "뉴스 조회 실패", "저장 뉴스 조회를 다시 시도하세요.", 0, 0, 0, null);
        }
    }
}
