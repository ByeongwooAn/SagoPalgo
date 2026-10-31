package com.sagopalgo.api.order.mapper;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;
@Mapper
public interface UnknownOrderReviewMapper {
    @Select("SELECT p.command_id FROM manual_order_review_preparations p LEFT JOIN manual_order_reviews r ON r.command_id=p.command_id LIMIT 1")
    String verifyStorage();
    @Select("SELECT * FROM manual_order_review_preparations WHERE command_id=#{id} AND user_id=#{user}")
    PreparationRow preparation(@Param("id") String id,@Param("user") Long user);
    @Insert("""
        INSERT INTO manual_order_review_preparations
          (command_id,user_id,review_id,account_fingerprint,token_hash,evidence_hash,evidence_json,expires_at,checked_at)
        VALUES (#{commandId},#{userId},#{reviewId},#{accountFingerprint},#{tokenHash},#{evidenceHash},#{evidenceJson},#{expiresAt},#{checkedAt})
        ON DUPLICATE KEY UPDATE review_id=#{reviewId},account_fingerprint=#{accountFingerprint},token_hash=#{tokenHash},
          evidence_hash=#{evidenceHash},evidence_json=#{evidenceJson},expires_at=#{expiresAt},checked_at=#{checkedAt}
        """) int prepare(PreparationRow row);
    @Select("SELECT * FROM manual_order_reviews WHERE review_id=#{id} AND user_id=#{user} AND command_id=#{command}")
    ReviewRow find(@Param("id") String id,@Param("user") Long user,@Param("command") String command);
    @Select("SELECT * FROM manual_order_reviews WHERE command_id=#{command} AND user_id=#{user} ORDER BY confirmed_at DESC,review_id DESC LIMIT 20")
    List<ReviewRow> recent(@Param("command") String command,@Param("user") Long user);
    @Delete("""
        DELETE FROM manual_order_review_preparations WHERE command_id=#{commandId} AND user_id=#{userId}
          AND review_id=#{reviewId} AND token_hash=#{tokenHash} AND evidence_hash=#{evidenceHash}
          AND account_fingerprint=#{accountFingerprint} AND expires_at>#{checkedAt}
        """) int consume(PreparationRow row);
    @Insert("""
        INSERT INTO manual_order_reviews (review_id,command_id,user_id,account_fingerprint,token_hash,evidence_json,confirmed_at)
        VALUES (#{reviewId},#{commandId},#{userId},#{accountFingerprint},#{tokenHash},#{evidenceJson},#{confirmedAt})
        """) int insert(ReviewRow row);
    record PreparationRow(String commandId,Long userId,String reviewId,String accountFingerprint,String tokenHash,
        String evidenceHash,String evidenceJson,LocalDateTime expiresAt,LocalDateTime checkedAt){}
    record ReviewRow(String reviewId,String commandId,Long userId,String accountFingerprint,String tokenHash,String evidenceJson,LocalDateTime confirmedAt){}
}
