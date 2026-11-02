package com.sagopalgo.api.kb.mapper;

import com.sagopalgo.api.kb.model.AccountObservationCollectorRecord;
import org.apache.ibatis.annotations.*;

@Mapper
public interface AccountObservationCollectorMapper {
    @Insert("""
        INSERT INTO kb_account_observation_collectors(user_id,account_binding,state,next_due_at)
        VALUES(#{user},#{binding},'IDLE',UTC_TIMESTAMP(6))
        ON DUPLICATE KEY UPDATE user_id=#{user}
        """)
    int initialize(@Param("user") Long user, @Param("binding") String binding);

    @Update("""
        UPDATE kb_account_observation_collectors SET state='ACTIVE',active_request_id=#{request},
          active_order_date=#{date},started_at=UTC_TIMESTAMP(6),completed_at=NULL,failure_code=NULL
        WHERE user_id=#{user} AND account_binding=#{binding} AND state='IDLE'
          AND next_due_at <= UTC_TIMESTAMP(6)
        """)
    int claim(@Param("user") Long user, @Param("binding") String binding,
        @Param("request") String request, @Param("date") String date);

    @Select("""
        SELECT user_id,account_binding,state,active_request_id,active_order_date,last_request_id,last_storage_state,
               last_snapshot_status,failure_code,next_due_at,started_at,completed_at
        FROM kb_account_observation_collectors WHERE user_id=#{user} AND account_binding=#{binding}
        """)
    @ConstructorArgs({
        @Arg(column="user_id",javaType=Long.class), @Arg(column="account_binding",javaType=String.class),
        @Arg(column="state",javaType=String.class), @Arg(column="active_request_id",javaType=String.class),
        @Arg(column="active_order_date",javaType=String.class), @Arg(column="last_request_id",javaType=String.class),
        @Arg(column="last_storage_state",javaType=String.class), @Arg(column="last_snapshot_status",javaType=String.class),
        @Arg(column="failure_code",javaType=String.class), @Arg(column="next_due_at",javaType=java.time.LocalDateTime.class),
        @Arg(column="started_at",javaType=java.time.LocalDateTime.class), @Arg(column="completed_at",javaType=java.time.LocalDateTime.class)
    })
    AccountObservationCollectorRecord find(@Param("user") Long user, @Param("binding") String binding);

    @Update("""
        UPDATE kb_account_observation_collectors SET state=#{state},last_request_id=active_request_id,
          last_storage_state=#{storage},last_snapshot_status=#{snapshot},failure_code=#{failure},
          active_request_id=NULL,active_order_date=NULL,completed_at=UTC_TIMESTAMP(6),
          next_due_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL #{interval} SECOND)
        WHERE user_id=#{user} AND account_binding=#{binding} AND state='ACTIVE'
          AND active_request_id=#{request} AND active_order_date=#{date}
        """)
    int finish(@Param("user") Long user, @Param("binding") String binding, @Param("request") String request,
        @Param("date") String date, @Param("state") String state, @Param("storage") String storage,
        @Param("snapshot") String snapshot, @Param("failure") String failure, @Param("interval") int interval);

    @Update("""
        UPDATE kb_account_observation_collectors SET state='IDLE',failure_code=NULL,
          next_due_at=DATE_ADD(UTC_TIMESTAMP(6),INTERVAL #{interval} SECOND)
        WHERE user_id=#{user} AND account_binding=#{binding} AND state='PAUSED' AND last_request_id=#{lastRequest}
        """)
    int resume(@Param("user") Long user, @Param("binding") String binding,
        @Param("lastRequest") String lastRequest, @Param("interval") int interval);
}
