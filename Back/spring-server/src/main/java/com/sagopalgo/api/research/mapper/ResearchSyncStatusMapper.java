package com.sagopalgo.api.research.mapper;

import com.sagopalgo.api.research.model.ResearchSyncStatusRecord;
import java.util.Optional;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * 관심 종목별 뉴스·공시 동기화 상태를 저장하고 조회합니다.
 */
@Mapper
public interface ResearchSyncStatusMapper {

    @Insert("""
        INSERT INTO research_sync_status (
          user_id, stock_code, stock_name, trigger_type, status,
          news_count, disclosure_count, provider_success_count,
          provider_failure_count, provider_disabled_count, message,
          last_attempted_at, last_succeeded_at
        ) VALUES (
          #{userId}, #{stockCode}, #{stockName}, #{triggerType}, #{status},
          #{newsCount}, #{disclosureCount}, #{providerSuccessCount},
          #{providerFailureCount}, #{providerDisabledCount}, #{message},
          #{lastAttemptedAt}, #{lastSucceededAt}
        )
        ON DUPLICATE KEY UPDATE
          stock_name = VALUES(stock_name),
          trigger_type = VALUES(trigger_type),
          status = VALUES(status),
          news_count = VALUES(news_count),
          disclosure_count = VALUES(disclosure_count),
          provider_success_count = VALUES(provider_success_count),
          provider_failure_count = VALUES(provider_failure_count),
          provider_disabled_count = VALUES(provider_disabled_count),
          message = VALUES(message),
          last_attempted_at = VALUES(last_attempted_at),
          last_succeeded_at = CASE
            WHEN VALUES(status) IN ('SUCCESS', 'PARTIAL') THEN VALUES(last_attempted_at)
            ELSE last_succeeded_at
          END,
          updated_at = CURRENT_TIMESTAMP
        """)
    int upsert(ResearchSyncStatusRecord record);

    @Select("""
        SELECT sync_status_id, user_id, stock_code, stock_name, trigger_type, status,
               news_count, disclosure_count, provider_success_count,
               provider_failure_count, provider_disabled_count, message,
               last_attempted_at, last_succeeded_at, created_at, updated_at
        FROM research_sync_status
        WHERE user_id = #{userId}
          AND stock_code = #{stockCode}
        """)
    Optional<ResearchSyncStatusRecord> findByUserIdAndStockCode(
        @Param("userId") Long userId,
        @Param("stockCode") String stockCode
    );
}
