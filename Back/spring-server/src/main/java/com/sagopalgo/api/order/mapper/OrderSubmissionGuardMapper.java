package com.sagopalgo.api.order.mapper;

import com.sagopalgo.api.order.model.OrderSubmissionGuardRecord;
import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

@Mapper
public interface OrderSubmissionGuardMapper {
    @Insert("""
        INSERT INTO order_submission_guards (
          order_approval_id, user_id, status, expires_at, created_at, updated_at
        )
        SELECT order_approval_id, user_id, 'READY', #{expiresAt}, #{now}, #{now}
        FROM order_approvals
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND status = 'ACKNOWLEDGED'
        """)
    int insertReady(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
        @Param("now") LocalDateTime now,
        @Param("expiresAt") LocalDateTime expiresAt
    );

    @Update("""
        UPDATE order_submission_guards
        SET status = 'RESERVED', reserved_at = #{now}, updated_at = #{now}
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND status = 'READY'
          AND expires_at > #{now}
          AND EXISTS (
            SELECT 1 FROM order_approvals a
            WHERE a.order_approval_id = order_submission_guards.order_approval_id
              AND a.user_id = #{userId}
              AND a.account_fingerprint = #{accountFingerprint}
          )
        """)
    int reserveOnce(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
        @Param("accountFingerprint") String accountFingerprint,
        @Param("now") LocalDateTime now
    );

    @Update("""
        UPDATE order_submission_guards
        SET status = 'UNCERTAIN', uncertain_at = #{now}, updated_at = #{now}
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND status = 'RESERVED'
        """)
    int markUncertain(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
        @Param("now") LocalDateTime now
    );

    @Select("""
        SELECT g.order_approval_id, g.user_id, g.status, g.expires_at,
               g.reserved_at, g.uncertain_at, g.created_at, g.updated_at,
               a.account_fingerprint
        FROM order_submission_guards g
        JOIN order_approvals a ON a.order_approval_id = g.order_approval_id
        WHERE g.order_approval_id = #{approvalId} AND g.user_id = #{userId}
        """)
    OrderSubmissionGuardRecord findByApprovalId(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId
    );
}
