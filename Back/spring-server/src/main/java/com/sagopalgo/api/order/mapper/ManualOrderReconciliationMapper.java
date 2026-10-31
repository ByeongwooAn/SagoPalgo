package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.ManualOrderReconciliationPreparation;
import com.sagopalgo.api.order.model.ManualOrderReconciliationRecord;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.*;

@Mapper
public interface ManualOrderReconciliationMapper {
    @Insert("""
        INSERT INTO manual_order_reconciliation_preparations
          (command_id,user_id,account_fingerprint,order_no,token_hash,expires_at,checked_at)
        VALUES (#{commandId},#{userId},#{accountFingerprint},#{orderNo},#{tokenHash},#{expiresAt},#{checkedAt})
        ON DUPLICATE KEY UPDATE account_fingerprint=#{accountFingerprint},order_no=#{orderNo},
          token_hash=#{tokenHash},expires_at=#{expiresAt},checked_at=#{checkedAt}
        """)
    int prepare(ManualOrderReconciliationPreparation preparation);

    @Select("SELECT * FROM manual_order_reconciliation_preparations WHERE command_id=#{id} AND user_id=#{userId}")
    ManualOrderReconciliationPreparation preparation(@Param("id") String id, @Param("userId") Long userId);

    @Delete("""
        DELETE FROM manual_order_reconciliation_preparations
        WHERE command_id=#{commandId} AND user_id=#{userId} AND token_hash=#{tokenHash}
          AND account_fingerprint=#{accountFingerprint} AND expires_at>#{now}
        """)
    int consume(@Param("commandId") String commandId, @Param("userId") Long userId,
        @Param("tokenHash") String tokenHash, @Param("accountFingerprint") String accountFingerprint,
        @Param("now") LocalDateTime now);

    @Select("SELECT * FROM manual_order_reconciliations WHERE command_id=#{id} AND user_id=#{userId}")
    ManualOrderReconciliationRecord find(@Param("id") String id, @Param("userId") Long userId);

    @Select("""
        SELECT COUNT(*) FROM manual_order_commands
        WHERE command_id<>#{commandId} AND account_fingerprint=#{accountFingerprint}
          AND order_date=#{orderDate} AND order_no=#{orderNo}
        """)
    int brokerOrderAlreadyRecorded(ManualOrderReconciliationRecord record);

    @Insert("""
        INSERT INTO manual_order_reconciliations
          (command_id,user_id,account_fingerprint,order_date,order_no,order_time,filled_quantity,confirmed_at)
        VALUES (#{commandId},#{userId},#{accountFingerprint},#{orderDate},#{orderNo},#{orderTime},#{filledQuantity},#{confirmedAt})
        """)
    int insert(ManualOrderReconciliationRecord record);
}
