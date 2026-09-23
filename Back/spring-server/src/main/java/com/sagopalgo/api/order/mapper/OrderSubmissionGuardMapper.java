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
          order_approval_id, user_id, status, created_at, updated_at
        )
        SELECT order_approval_id, user_id, 'READY', #{now}, #{now}
        FROM order_approvals
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND status = 'ACKNOWLEDGED'
        """)
    int insertReady(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
        @Param("now") LocalDateTime now
    );

    @Update("""
        UPDATE order_submission_guards
        SET status = 'RESERVED', reserved_at = #{now}, updated_at = #{now}
        WHERE order_approval_id = #{approvalId}
          AND user_id = #{userId}
          AND status = 'READY'
        """)
    int reserveOnce(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId,
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
        SELECT order_approval_id, user_id, status, reserved_at, uncertain_at,
               created_at, updated_at
        FROM order_submission_guards
        WHERE order_approval_id = #{approvalId} AND user_id = #{userId}
        """)
    OrderSubmissionGuardRecord findByApprovalId(
        @Param("approvalId") Long approvalId,
        @Param("userId") Long userId
    );
}
