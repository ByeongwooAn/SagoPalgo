package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.ManualOrderDispatchRecord;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.*;

@Mapper
public interface ManualOrderDispatchMapper {
    @Insert("""
        INSERT INTO manual_order_dispatches (command_id,user_id,execution_key,phase,reserved_at)
        VALUES (#{commandId},#{userId},#{executionKey},'RESERVED',#{now})
        """)
    int reserve(@Param("commandId") String commandId, @Param("userId") Long userId,
        @Param("executionKey") String executionKey, @Param("now") LocalDateTime now);

    @Update("""
        UPDATE manual_order_dispatches SET phase='DISPATCHING',started_at=#{now}
        WHERE command_id=#{commandId} AND user_id=#{userId} AND execution_key=#{executionKey} AND phase='RESERVED'
        """)
    int begin(@Param("commandId") String commandId, @Param("userId") Long userId,
        @Param("executionKey") String executionKey, @Param("now") LocalDateTime now);

    @Update("""
        UPDATE manual_order_dispatches SET phase='RETURNED',outcome_status=#{status},order_no=#{orderNo},
          result_code=#{resultCode},process_code=#{processCode},returned_at=#{now}
        WHERE command_id=#{commandId} AND user_id=#{userId} AND execution_key=#{executionKey}
          AND (phase='DISPATCHING' OR (phase='RESERVED' AND #{status}='UNKNOWN'))
        """)
    int returned(@Param("commandId") String commandId, @Param("userId") Long userId, @Param("executionKey") String executionKey,
        @Param("status") String status, @Param("orderNo") String orderNo, @Param("resultCode") String resultCode,
        @Param("processCode") String processCode, @Param("now") LocalDateTime now);

    @Select("SELECT * FROM manual_order_dispatches WHERE command_id=#{commandId} AND user_id=#{userId}")
    ManualOrderDispatchRecord find(@Param("commandId") String commandId, @Param("userId") Long userId);

    @Select("SELECT * FROM manual_order_dispatches WHERE command_id=#{commandId} AND user_id=#{userId} FOR UPDATE")
    ManualOrderDispatchRecord lock(@Param("commandId") String commandId, @Param("userId") Long userId);

    @Select("SELECT recovered_at FROM manual_order_dispatch_recoveries WHERE command_id=#{commandId} AND user_id=#{userId}")
    LocalDateTime recoveredAt(@Param("commandId") String commandId, @Param("userId") Long userId);

    @Insert("""
        INSERT INTO manual_order_dispatch_recoveries (command_id,user_id,previous_status,recovered_status,order_no,recovered_at)
        VALUES (#{commandId},#{userId},'SENDING',#{status},#{orderNo},#{now})
        """)
    int audit(@Param("commandId") String commandId, @Param("userId") Long userId, @Param("status") String status,
        @Param("orderNo") String orderNo, @Param("now") LocalDateTime now);
}
