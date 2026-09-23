package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderApprovalRecord;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderApprovalMapper {
    @Insert("""
        INSERT INTO order_approvals (
          user_id, order_precheck_id, token_hash, status, expires_at, created_at
        ) VALUES (
          #{userId}, #{orderPrecheckId}, #{tokenHash}, 'PREPARED', #{expiresAt}, #{createdAt}
        )
        """)
    @Options(useGeneratedKeys = true, keyProperty = "orderApprovalId", keyColumn = "order_approval_id")
    int insert(OrderApprovalRecord record);

    @Update("""
        UPDATE order_approvals
        SET status = 'ACKNOWLEDGED', acknowledged_at = #{now}
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND token_hash = #{tokenHash}
          AND status = 'PREPARED'
          AND expires_at > #{now}
        """)
    int acknowledge(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
        @Param("tokenHash") String tokenHash,
        @Param("now") LocalDateTime now
    );
}
