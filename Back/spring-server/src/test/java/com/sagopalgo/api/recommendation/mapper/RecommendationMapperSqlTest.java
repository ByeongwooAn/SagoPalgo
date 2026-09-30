package com.sagopalgo.api.recommendation.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Select;
import org.junit.jupiter.api.Test;

class RecommendationMapperSqlTest {
    @Test
    void storesAnalysisContextAndKeepsWatchlistOutOfPortfolioHeadline() throws Exception {
        String insert = String.join(" ", RecommendationMapper.class
            .getMethod("insert", com.sagopalgo.api.recommendation.model.RecommendationRecord.class)
            .getAnnotation(Insert.class).value());
        String latest = String.join(" ", RecommendationMapper.class
            .getMethod("findLatestByUserId", Long.class)
            .getAnnotation(Select.class).value());

        assertThat(insert).contains("analysis_context", "#{analysisContext}");
        assertThat(latest).contains("analysis_context = 'HOLDING'");
    }
}
