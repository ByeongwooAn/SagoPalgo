package com.sagopalgo.api.research.mapper;

import com.sagopalgo.api.research.model.ResearchNewsRecord;
import java.time.LocalDate;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * research_news 테이블에 접근하는 MyBatis Mapper입니다.
 */
@Mapper
public interface ResearchNewsMapper {

    @Insert("""
        INSERT INTO research_news (
          provider, content_key, stock_code, stock_name, title, link, summary, published_at
        ) VALUES (
          #{provider}, #{contentKey}, #{stockCode}, #{stockName}, #{title}, #{link}, #{summary}, #{publishedAt}
        )
        ON DUPLICATE KEY UPDATE
          stock_code = VALUES(stock_code),
          stock_name = VALUES(stock_name),
          title = VALUES(title),
          link = VALUES(link),
          summary = VALUES(summary),
          published_at = VALUES(published_at),
          updated_at = CURRENT_TIMESTAMP
        """)
    int upsert(ResearchNewsRecord record);

    @Select("""
        SELECT news_id, provider, content_key, stock_code, stock_name, title, link, summary,
               published_at, created_at, updated_at
        FROM research_news
        WHERE stock_code = #{stockCode}
          AND (
            published_at IS NULL
            OR (published_at >= #{fromDate} AND published_at < DATE_ADD(#{toDate}, INTERVAL 1 DAY))
          )
        ORDER BY published_at IS NULL, published_at DESC, news_id DESC
        """)
    List<ResearchNewsRecord> findByStockCodeAndDateRange(
        @Param("stockCode") String stockCode,
        @Param("fromDate") LocalDate fromDate,
        @Param("toDate") LocalDate toDate
    );
}
