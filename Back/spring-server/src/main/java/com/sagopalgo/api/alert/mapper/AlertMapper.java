package com.sagopalgo.api.alert.mapper;

import com.sagopalgo.api.alert.model.AlertRecord;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Result;
import org.apache.ibatis.annotations.ResultMap;
import org.apache.ibatis.annotations.Results;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

/**
 * alerts 테이블의 생성, 조회, 전달 및 읽음 상태 변경을 담당합니다.
 */
@Mapper
public interface AlertMapper {

    @Insert("""
        INSERT INTO alerts (
          user_id, recommendation_id, alert_type, event_type, event_key,
          stock_code, market, title, body
        ) VALUES (
          #{userId}, #{recommendationId}, #{alertType}, #{eventType}, #{eventKey},
          #{stockCode}, #{market}, #{title}, #{body}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "alertId", keyColumn = "alert_id")
    int insert(AlertRecord record);

    @Insert("""
        INSERT IGNORE INTO alerts (
          user_id, recommendation_id, alert_type, event_type, event_key,
          stock_code, market, title, body
        ) VALUES (
          #{userId}, NULL, #{alertType}, #{eventType}, #{eventKey},
          #{stockCode}, #{market}, #{title}, #{body}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "alertId", keyColumn = "alert_id")
    int insertEvent(AlertRecord record);

    @Select("""
        <script>
        SELECT alert_id, user_id, recommendation_id, alert_type, event_type, event_key,
               stock_code, market, title, body,
               is_read, sent_at, created_at, updated_at
        FROM alerts
        WHERE user_id = #{userId}
        <if test='unreadOnly'>
          AND is_read = FALSE
        </if>
        ORDER BY created_at DESC, alert_id DESC
        LIMIT #{size} OFFSET #{offset}
        </script>
        """)
    @Results(id = "alertRecordMap", value = {
        @Result(column = "is_read", property = "read")
    })
    List<AlertRecord> findPage(
        @Param("userId") Long userId,
        @Param("unreadOnly") boolean unreadOnly,
        @Param("size") int size,
        @Param("offset") int offset
    );

    @Select("""
        <script>
        SELECT COUNT(*)
        FROM alerts
        WHERE user_id = #{userId}
        <if test='unreadOnly'>
          AND is_read = FALSE
        </if>
        </script>
        """)
    long count(@Param("userId") Long userId, @Param("unreadOnly") boolean unreadOnly);

    @Select("""
        SELECT alert_id, user_id, recommendation_id, alert_type, event_type, event_key,
               stock_code, market, title, body,
               is_read, sent_at, created_at, updated_at
        FROM alerts
        WHERE user_id = #{userId}
          AND sent_at IS NULL
        ORDER BY created_at, alert_id
        LIMIT #{limit}
        """)
    @ResultMap("alertRecordMap")
    List<AlertRecord> findPending(@Param("userId") Long userId, @Param("limit") int limit);

    @Select("""
        SELECT alert_id, user_id, recommendation_id, alert_type, event_type, event_key,
               stock_code, market, title, body,
               is_read, sent_at, created_at, updated_at
        FROM alerts
        WHERE alert_id = #{alertId}
          AND user_id = #{userId}
        """)
    @ResultMap("alertRecordMap")
    Optional<AlertRecord> findByIdAndUserId(
        @Param("alertId") Long alertId,
        @Param("userId") Long userId
    );

    @Select("""
        SELECT COUNT(*)
        FROM alerts a
        JOIN recommendations r ON r.recommendation_id = a.recommendation_id
        WHERE a.user_id = #{userId}
          AND r.stock_code = #{stockCode}
          AND r.market = #{market}
          AND a.alert_type = #{alertType}
          AND a.created_at >= #{cutoff}
        """)
    boolean existsRecentSignal(
        @Param("userId") Long userId,
        @Param("stockCode") String stockCode,
        @Param("market") String market,
        @Param("alertType") String alertType,
        @Param("cutoff") LocalDateTime cutoff
    );

    @Select("""
        SELECT COUNT(*)
        FROM alerts
        WHERE user_id = #{userId}
          AND stock_code = #{stockCode}
          AND market = #{market}
          AND event_type = #{eventType}
          AND created_at >= #{cutoff}
        """)
    boolean existsRecentEvent(
        @Param("userId") Long userId,
        @Param("stockCode") String stockCode,
        @Param("market") String market,
        @Param("eventType") String eventType,
        @Param("cutoff") LocalDateTime cutoff
    );

    @Update("""
        UPDATE alerts
        SET sent_at = COALESCE(sent_at, CURRENT_TIMESTAMP)
        WHERE alert_id = #{alertId}
          AND user_id = #{userId}
        """)
    int markSent(@Param("alertId") Long alertId, @Param("userId") Long userId);

    @Update("""
        UPDATE alerts
        SET is_read = TRUE
        WHERE alert_id = #{alertId}
          AND user_id = #{userId}
        """)
    int markRead(@Param("alertId") Long alertId, @Param("userId") Long userId);
}
