package com.sagopalgo.api.order.simulation;

import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface OrderSimulationMapper {
    record Row(String sessionId, Long userId, String stateJson, long revision, LocalDateTime createdAt, LocalDateTime updatedAt) {}

    @Insert("""
        INSERT INTO order_simulation_sessions (session_id,user_id,state_json,revision,created_at,updated_at)
        VALUES (#{sessionId},#{userId},#{stateJson},0,#{createdAt},#{updatedAt})
        """)
    int insert(Row row);

    @Select("SELECT * FROM order_simulation_sessions WHERE session_id=#{id} AND user_id=#{userId}")
    Row find(@Param("id") String id, @Param("userId") Long userId);

    @Select("SELECT * FROM order_simulation_sessions WHERE session_id=#{id} AND user_id=#{userId} FOR UPDATE")
    Row lock(@Param("id") String id, @Param("userId") Long userId);

    @Select("SELECT * FROM order_simulation_sessions WHERE user_id=#{userId} ORDER BY created_at DESC, session_id DESC LIMIT 20")
    List<Row> recent(Long userId);

    @Update("""
        UPDATE order_simulation_sessions SET state_json=#{stateJson},revision=revision+1,updated_at=#{updatedAt}
        WHERE session_id=#{sessionId} AND user_id=#{userId} AND revision=#{revision}
        """)
    int update(Row row);
}
