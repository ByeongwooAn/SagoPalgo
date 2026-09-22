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

    @Insert("""
        INSERT INTO recommendations (
          user_id, stock_code, stock_name, market, recommendation_type, status,
          score, entry_price, stop_loss_rate, take_profit_rate, ai_summary
        ) VALUES (
          #{userId}, #{stockCode}, #{stockName}, #{market}, #{recommendationType}, #{status},
          #{score}, #{entryPrice}, #{stopLossRate}, #{takeProfitRate}, #{aiSummary}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "recommendationId", keyColumn = "recommendation_id")
    int insert(RecommendationRecord record);

    @Select("""
        SELECT recommendation_id, user_id, stock_code, stock_name, market,
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
        SELECT recommendation_id, user_id, stock_code, stock_name, market,
               recommendation_type, status, score, entry_price, stop_loss_rate,
               take_profit_rate, ai_summary, created_at, updated_at
        FROM recommendations
        WHERE user_id = #{userId}
        ORDER BY created_at DESC, recommendation_id DESC
        LIMIT 1
        """)
    Optional<RecommendationRecord> findLatestByUserId(@Param("userId") Long userId);

    @Select("""
        <script>
        SELECT recommendation_id, user_id, stock_code, stock_name, market,
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
