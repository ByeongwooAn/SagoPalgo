package com.sagopalgo.api.research.mapper;

import com.sagopalgo.api.research.model.ResearchDisclosureRecord;
import java.time.LocalDate;
import java.util.List;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

/**
 * research_disclosures 테이블에 접근하는 MyBatis Mapper입니다.
 */
@Mapper
public interface ResearchDisclosureMapper {
    @Select("SELECT * FROM research_disclosures WHERE provider=#{provider} AND stock_code=#{stock} AND receipt_number=#{receipt}")
    ResearchDisclosureRecord findByReceipt(@Param("provider") String provider,@Param("stock") String stock,@Param("receipt") String receipt);

    @Insert("""
        INSERT INTO research_disclosures (
          provider, stock_code, corp_code, corp_name, report_name, receipt_number,
          submitter_name, receipt_date, link
        ) VALUES (
          #{provider}, #{stockCode}, #{corpCode}, #{corpName}, #{reportName}, #{receiptNumber},
          #{submitterName}, #{receiptDate}, #{link}
        )
        ON DUPLICATE KEY UPDATE
          stock_code = VALUES(stock_code),
          corp_code = VALUES(corp_code),
          corp_name = VALUES(corp_name),
          report_name = VALUES(report_name),
          submitter_name = VALUES(submitter_name),
          receipt_date = VALUES(receipt_date),
          link = VALUES(link),
          updated_at = CURRENT_TIMESTAMP
        """)
    int upsert(ResearchDisclosureRecord record);

    @Select("""
        SELECT disclosure_id, provider, stock_code, corp_code, corp_name, report_name,
               receipt_number, submitter_name, receipt_date, link, created_at, updated_at
        FROM research_disclosures
        WHERE stock_code = #{stockCode}
          AND (
            receipt_date IS NULL
            OR receipt_date BETWEEN #{fromDate} AND #{toDate}
          )
        ORDER BY receipt_date IS NULL, receipt_date DESC, disclosure_id DESC
        """)
    List<ResearchDisclosureRecord> findByStockCodeAndDateRange(
        @Param("stockCode") String stockCode,
        @Param("fromDate") LocalDate fromDate,
        @Param("toDate") LocalDate toDate
    );
}
