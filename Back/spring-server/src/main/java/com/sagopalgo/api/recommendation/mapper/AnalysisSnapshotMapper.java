package com.sagopalgo.api.recommendation.mapper;

import com.sagopalgo.api.recommendation.model.AnalysisSnapshotRecord;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;

/**
 * analysis_snapshots 테이블 접근 Mapper입니다.
 */
@Mapper
public interface AnalysisSnapshotMapper {

    @Insert("""
        INSERT INTO analysis_snapshots (
          user_id, recommendation_id, stock_code, market, analysis_type, score, raw_payload
        ) VALUES (
          #{userId}, #{recommendationId}, #{stockCode}, #{market}, #{analysisType},
          #{score}, #{rawPayload}
        )
        """)
    int insert(AnalysisSnapshotRecord record);
}
