package com.sagopalgo.api.order.mapper;
import com.sagopalgo.api.order.model.ManualOrderDiagnosticRecord;
import java.time.LocalDateTime;
import java.util.List;
import org.apache.ibatis.annotations.*;
@Mapper
public interface ManualOrderDiagnosticMapper {
    @Select("SELECT diagnostic_id FROM manual_order_diagnostics LIMIT 1") String verifyStorage();
    @Insert("""
        INSERT INTO manual_order_diagnostics (diagnostic_id,command_id,user_id,order_no,phase_before,state,created_at)
        VALUES (#{diagnosticId},#{commandId},#{userId},#{orderNo},#{phaseBefore},'REQUESTED',#{createdAt})
        """) int insert(ManualOrderDiagnosticRecord row);
    @Select("SELECT * FROM manual_order_diagnostics WHERE diagnostic_id=#{id} AND user_id=#{user}")
    ManualOrderDiagnosticRecord find(@Param("id") String id,@Param("user") Long user);
    @Select("SELECT * FROM manual_order_diagnostics WHERE command_id=#{command} AND user_id=#{user} ORDER BY created_at DESC,diagnostic_id DESC LIMIT 20")
    List<ManualOrderDiagnosticRecord> recent(@Param("command") String command,@Param("user") Long user);
    @Update("""
        UPDATE manual_order_diagnostics SET state='COMPLETED',report_json=#{report},completed_at=#{now}
        WHERE diagnostic_id=#{id} AND user_id=#{user} AND state='REQUESTED'
        """) int complete(@Param("id") String id,@Param("user") Long user,@Param("report") String report,@Param("now") LocalDateTime now);
}
