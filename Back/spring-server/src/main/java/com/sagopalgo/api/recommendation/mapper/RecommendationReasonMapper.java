package com.sagopalgo.api.recommendation.mapper;

import com.sagopalgo.api.recommendation.model.RecommendationReasonRecord;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * recommendation_reasons 테이블 접근 Mapper입니다.
 */
@Mapper
public interface RecommendationReasonMapper {

    @Insert("""
        INSERT INTO recommendation_reasons (
          recommendation_id, reason_type, label, description, score
        ) VALUES (
          #{recommendationId}, #{reasonType}, #{label}, #{description}, #{score}
        )
        """)
    int insert(RecommendationReasonRecord record);

    @Select("""
        SELECT reason_id, recommendation_id, reason_type, label, description, score
        FROM recommendation_reasons
        WHERE recommendation_id = #{recommendationId}
        ORDER BY reason_id
        """)
    List<RecommendationReasonRecord> findByRecommendationId(
        @Param("recommendationId") Long recommendationId
    );
}
