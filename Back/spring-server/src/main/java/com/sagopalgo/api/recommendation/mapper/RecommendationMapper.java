package com.sagopalgo.api.recommendation.mapper;

import com.sagopalgo.api.recommendation.model.RecommendationRecord;
import java.util.List;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * recommendations 테이블 접근 Mapper입니다.
 */
@Mapper
public interface RecommendationMapper {

    String EVIDENCE = """
        (SELECT CASE WHEN JSON_VALID(a.raw_payload) THEN JSON_OBJECT(
          'modelVersion', JSON_UNQUOTE(JSON_EXTRACT(a.raw_payload, '$.analysis.modelVersion')),
          'candleCount', JSON_LENGTH(JSON_EXTRACT(a.raw_payload, '$.request.candles')),
          'newsCount', JSON_LENGTH(JSON_EXTRACT(a.raw_payload, '$.request.news')),
          'disclosureCount', JSON_LENGTH(JSON_EXTRACT(a.raw_payload, '$.request.disclosures'))
        ) ELSE NULL END FROM analysis_snapshots a
        WHERE a.recommendation_id = recommendations.recommendation_id
          AND a.user_id = recommendations.user_id ORDER BY a.snapshot_id DESC LIMIT 1) AS analysis_evidence,
        """;

    @Insert("""
        INSERT INTO recommendations (
          user_id, stock_code, stock_name, market, analysis_context, recommendation_type, status,
          score, entry_price, stop_loss_rate, take_profit_rate, ai_summary
        ) VALUES (
          #{userId}, #{stockCode}, #{stockName}, #{market}, #{analysisContext}, #{recommendationType}, #{status},
          #{score}, #{entryPrice}, #{stopLossRate}, #{takeProfitRate}, #{aiSummary}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "recommendationId", keyColumn = "recommendation_id")
    int insert(RecommendationRecord record);

    @Select("SELECT " + EVIDENCE + """
        recommendation_id, user_id, stock_code, stock_name, market, analysis_context,
               recommendation_type, status, score, entry_price, stop_loss_rate,
               take_profit_rate, ai_summary, created_at, updated_at
        FROM recommendations
        WHERE recommendation_id = #{recommendationId}
          AND user_id = #{userId}
        """)
    Optional<RecommendationRecord> findByIdAndUserId(
        @Param("recommendationId") Long recommendationId,
        @Param("userId") Long userId
    );

    @Select("""
        SELECT recommendation_id, user_id, stock_code, stock_name, market, analysis_context,
               recommendation_type, status, score, entry_price, stop_loss_rate,
               take_profit_rate, ai_summary, created_at, updated_at
        FROM recommendations
        WHERE user_id = #{userId}
          AND analysis_context = 'HOLDING'
        ORDER BY created_at DESC, recommendation_id DESC
        LIMIT 1
        """)
    Optional<RecommendationRecord> findLatestByUserId(@Param("userId") Long userId);

    @Select("SELECT " + EVIDENCE + """
        recommendation_id, user_id, stock_code, stock_name, market, analysis_context,
        recommendation_type, status, score, entry_price, stop_loss_rate,
        take_profit_rate, ai_summary, created_at, updated_at
        FROM recommendations
        WHERE user_id = #{userId}
          AND ((analysis_context = 'HOLDING' AND EXISTS (
              SELECT 1 FROM holdings h WHERE h.user_id = recommendations.user_id
                AND h.stock_code = recommendations.stock_code AND h.market = recommendations.market AND h.status != 'SOLD'))
            OR (analysis_context = 'WATCHLIST' AND EXISTS (
              SELECT 1 FROM watchlist w WHERE w.user_id = recommendations.user_id
                AND w.stock_code = recommendations.stock_code AND w.market = recommendations.market)))
        ORDER BY created_at DESC, recommendation_id DESC LIMIT 1
        """)
    Optional<RecommendationRecord> findLatestRelevantByUserId(@Param("userId") Long userId);

    @Select("<script> SELECT " + EVIDENCE + """
        recommendation_id, user_id, stock_code, stock_name, market, analysis_context,
               recommendation_type, status, score, entry_price, stop_loss_rate,
               take_profit_rate, ai_summary, created_at, updated_at
        FROM recommendations
        WHERE user_id = #{userId}
        <if test='status != null and status != ""'>
          AND status = #{status}
        </if>
        ORDER BY created_at DESC, recommendation_id DESC
        LIMIT #{size} OFFSET #{offset}
        </script>
        """)
    List<RecommendationRecord> findPage(
        @Param("userId") Long userId,
        @Param("status") String status,
        @Param("size") int size,
        @Param("offset") int offset
    );

    @Select("""
        <script>
        SELECT COUNT(*)
        FROM recommendations
        WHERE user_id = #{userId}
        <if test='status != null and status != ""'>
          AND status = #{status}
        </if>
        </script>
        """)
    long count(@Param("userId") Long userId, @Param("status") String status);
}
