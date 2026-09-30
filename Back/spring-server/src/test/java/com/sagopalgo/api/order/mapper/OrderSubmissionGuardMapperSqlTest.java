package com.sagopalgo.api.order.mapper;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDateTime;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Update;
import org.junit.jupiter.api.Test;

class OrderSubmissionGuardMapperSqlTest {
    @Test
    void insertsAnExpiryAndReservesOnlyBeforeIt() throws Exception {
        String insert = String.join(" ", OrderSubmissionGuardMapper.class
            .getMethod("insertReady", Long.class, Long.class, LocalDateTime.class, LocalDateTime.class)
            .getAnnotation(Insert.class).value());
        String reserve = String.join(" ", OrderSubmissionGuardMapper.class
            .getMethod("reserveOnce", Long.class, Long.class, String.class, LocalDateTime.class)
            .getAnnotation(Update.class).value());

        assertThat(insert).contains("expires_at", "#{expiresAt}");
        assertThat(reserve).contains("status = 'READY'", "expires_at > #{now}",
            "a.account_fingerprint = #{accountFingerprint}");
    }
}
