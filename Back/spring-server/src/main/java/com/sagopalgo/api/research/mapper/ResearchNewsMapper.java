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

    @Select("""
        SELECT n.news_id, n.provider, n.content_key, n.stock_code, n.stock_name, n.title, n.link,
               n.summary, n.published_at, n.created_at, n.updated_at
        FROM research_news n
        WHERE n.published_at >= #{from} AND n.published_at <= #{to}
          AND (EXISTS (SELECT 1 FROM holdings h WHERE h.user_id = #{userId}
                       AND h.stock_code = n.stock_code AND h.status != 'SOLD')
            OR EXISTS (SELECT 1 FROM watchlist w WHERE w.user_id = #{userId} AND w.stock_code = n.stock_code))
        ORDER BY n.published_at DESC, n.news_id DESC
        LIMIT 200
        """)
    List<ResearchNewsRecord> findRecentForUser(@Param("userId") Long userId,
        @Param("from") java.time.Instant from, @Param("to") java.time.Instant to);

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
