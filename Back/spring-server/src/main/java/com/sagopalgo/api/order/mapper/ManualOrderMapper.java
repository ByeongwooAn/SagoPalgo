package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.ManualOrderCommand;
import com.sagopalgo.api.order.dto.ManualOrderObservation;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;

@Mapper
public interface ManualOrderMapper {
    @Select("SELECT c.command_id FROM manual_order_commands c LEFT JOIN manual_order_observations o ON o.command_id=c.command_id LIMIT 1")
    String verifyStorage();

    // 같은 사용자의 동시 신규 주문·정정 준비를 직렬화합니다. HTTP 호출 중에는 DB 잠금을 유지하지 않습니다.
    @Select("SELECT user_id FROM users WHERE user_id = #{userId} FOR UPDATE")
    Long lockUser(Long userId);

    @Select("SELECT COUNT(*) FROM manual_order_commands WHERE user_id=#{userId} AND status IN ('SENDING','UNKNOWN')")
    int pending(Long userId);

    @Insert("""
        INSERT INTO manual_order_commands (command_id,user_id,approval_id,parent_id,kind,stock_code,stock_name,
          market,side,price,quantity,account_fingerprint,token_hash,expires_at,status,order_date,created_at,updated_at)
        VALUES (#{commandId},#{userId},#{approvalId},#{parentId},#{kind},#{stockCode},#{stockName},#{market},#{side},
          #{price},#{quantity},#{accountFingerprint},#{tokenHash},#{expiresAt},#{status},#{orderDate},#{createdAt},#{updatedAt})
        """)
    int insert(ManualOrderCommand command);

    @Select("SELECT * FROM manual_order_commands WHERE command_id=#{id} AND user_id=#{userId}")
    ManualOrderCommand find(@Param("id") String id, @Param("userId") Long userId);

    @Select("SELECT * FROM manual_order_commands WHERE approval_id=#{approvalId} AND user_id=#{userId}")
    ManualOrderCommand findApproval(@Param("approvalId") Long approvalId, @Param("userId") Long userId);

    @Select("SELECT * FROM manual_order_commands WHERE user_id=#{userId} ORDER BY created_at DESC,command_id DESC LIMIT 100")
    List<ManualOrderCommand> recent(Long userId);

    @Update("""
        UPDATE manual_order_commands SET status=#{status}, order_no=#{orderNo}, result_code=#{resultCode},
          process_code=#{processCode}, updated_at=#{now} WHERE command_id=#{id} AND user_id=#{userId} AND status='SENDING'
        """)
    int finish(@Param("id") String id, @Param("userId") Long userId, @Param("status") String status,
        @Param("orderNo") String orderNo, @Param("resultCode") String resultCode,
        @Param("processCode") String processCode, @Param("now") LocalDateTime now);

    @Update("""
        UPDATE manual_order_commands SET change_id=#{child},updated_at=#{now}
        WHERE command_id=#{parent} AND user_id=#{userId} AND status='ACCEPTED' AND change_id IS NULL AND kind='NEW'
        """)
    int claimParent(@Param("parent") String parent, @Param("child") String child,
        @Param("userId") Long userId, @Param("now") LocalDateTime now);

    @Update("""
        UPDATE manual_order_commands SET status='SENDING',updated_at=#{now}
        WHERE command_id=#{id} AND user_id=#{userId} AND status='PREPARED' AND expires_at>#{now}
          AND token_hash=#{hash} AND account_fingerprint=#{fingerprint}
        """)
    int claimChange(@Param("id") String id, @Param("userId") Long userId, @Param("hash") String hash,
        @Param("fingerprint") String fingerprint, @Param("now") LocalDateTime now);

    @Insert("""
        INSERT INTO manual_order_observations (command_id,status,complete_scan,filled_quantity,open_quantity,checked_at)
        VALUES (#{commandId},#{status},#{completeScan},#{filledQuantity},#{openQuantity},#{checkedAt})
        """)
    int observe(ManualOrderObservation observation);

    @Select("""
        SELECT command_id,status,complete_scan,filled_quantity,open_quantity,checked_at
        FROM manual_order_observations WHERE command_id=#{id} ORDER BY observation_id DESC LIMIT 20
        """)
    List<ManualOrderObservation> observations(String id);
}
