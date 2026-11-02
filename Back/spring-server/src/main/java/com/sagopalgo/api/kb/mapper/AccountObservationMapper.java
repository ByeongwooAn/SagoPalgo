package com.sagopalgo.api.kb.mapper;

import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface AccountObservationMapper {
    String COLUMNS = "record_id,user_id,request_id,account_binding,order_date,storage_state,observation_id,"
        + "snapshot_status,payload,payload_sha256,failure_code,created_at,completed_at";

    @Insert("""
        INSERT INTO kb_account_observations
          (user_id,request_id,account_binding,order_date,storage_state,created_at)
        VALUES (#{user},#{request},#{binding},#{date},'PENDING',#{now})
        """)
    int reserve(@Param("user") Long user, @Param("request") String request,
        @Param("binding") String binding, @Param("date") String date, @Param("now") LocalDateTime now);

    @Select("SELECT " + COLUMNS + " FROM kb_account_observations WHERE user_id=#{user} AND request_id=#{request}")
    @Results(id = "observationRecord")
    @ConstructorArgs({
        @Arg(column="record_id", javaType=Long.class), @Arg(column="user_id", javaType=Long.class),
        @Arg(column="request_id", javaType=String.class), @Arg(column="account_binding", javaType=String.class),
        @Arg(column="order_date", javaType=String.class), @Arg(column="storage_state", javaType=String.class),
        @Arg(column="observation_id", javaType=String.class), @Arg(column="snapshot_status", javaType=String.class),
        @Arg(column="payload", javaType=String.class), @Arg(column="payload_sha256", javaType=String.class),
        @Arg(column="failure_code", javaType=String.class), @Arg(column="created_at", javaType=LocalDateTime.class),
        @Arg(column="completed_at", javaType=LocalDateTime.class)
    })
    AccountObservationRecord findRequest(@Param("user") Long user, @Param("request") String request);

    @Select("SELECT " + COLUMNS + " FROM kb_account_observations WHERE user_id=#{user} "
        + "AND account_binding=#{binding} AND request_id=#{request}")
    @ResultMap("observationRecord")
    AccountObservationRecord findScoped(@Param("user") Long user, @Param("binding") String binding,
        @Param("request") String request);

    @Select("""
        <script>
        SELECT record_id,user_id,request_id,account_binding,order_date,storage_state,observation_id,
               snapshot_status,NULL AS payload,NULL AS payload_sha256,failure_code,created_at,completed_at
        FROM kb_account_observations WHERE user_id=#{user} AND account_binding=#{binding}
        <if test="before != null">AND record_id &lt; #{before}</if>
        ORDER BY record_id DESC LIMIT #{limit}
        </script>
        """)
    @ResultMap("observationRecord")
    List<AccountObservationRecord> recent(@Param("user") Long user, @Param("binding") String binding,
        @Param("before") Long before, @Param("limit") int limit);

    @Update("""
        UPDATE kb_account_observations SET storage_state='COMPLETED', observation_id=#{observation},
          snapshot_status=#{status},payload=#{payload},payload_sha256=#{hash},completed_at=#{now}
        WHERE user_id=#{user} AND request_id=#{request} AND account_binding=#{binding} AND storage_state='PENDING'
        """)
    int complete(@Param("user") Long user, @Param("request") String request, @Param("binding") String binding,
        @Param("observation") String observation, @Param("status") String status, @Param("payload") String payload,
        @Param("hash") String hash, @Param("now") LocalDateTime now);

    @Update("""
        UPDATE kb_account_observations SET storage_state='FAILED',failure_code=#{code},completed_at=#{now}
        WHERE user_id=#{user} AND request_id=#{request} AND account_binding=#{binding} AND storage_state='PENDING'
        """)
    int fail(@Param("user") Long user, @Param("request") String request, @Param("binding") String binding,
        @Param("code") String code, @Param("now") LocalDateTime now);
}
