package com.sagopalgo.api.research.export;

import com.fasterxml.jackson.databind.*;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.common.util.ContentHash;
import com.sagopalgo.api.market.stream.MarketStreamEvent;
import com.sagopalgo.api.research.model.*;
import java.time.*;
import java.time.temporal.ChronoUnit;
import java.util.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.*;

/** Existing public-data tables only. No provider, account, subscription, or order dependency. */
@Service
public class StoredDatasetExportService {
    public static final int MAX_ROWS = 10000;
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    public StoredDatasetExportService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json.copy().enable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);
    }
    public record StreamRow(String eventId, String stockCode, String type, Instant marketAt,
        Instant receivedAt, String payloadJson, String contentHash) {}
    public record VersionRow(long changeId, String kind, String provider, String stockCode, String itemKey,
        long revision, Instant observedAt, String origin, String payloadJson, String contentHash) {}
    public record Snapshot(String schemaVersion, String stockCode, Instant from, Instant to, Instant exportedAt,
        boolean readOnly, boolean usableForTrading, String consistency, String streamCoverage, String researchScope,
        List<StreamRow> streamEvents, List<VersionRow> researchVersions) {}

    @Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ, timeout = 30)
    public Snapshot export(String stock, Instant from, Instant to) {
        if (stock == null || !stock.matches("[0-9]{6}") || from == null || to == null || !from.isBefore(to)
            || Duration.between(from, to).compareTo(Duration.ofDays(1)) > 0
            || !from.equals(from.truncatedTo(ChronoUnit.MINUTES)) || !to.equals(to.truncatedTo(ChronoUnit.MINUTES)))
            throw new ApiException(ErrorCode.VALIDATION_ERROR, "종목과 1일 이내의 분 단위 UTC 조회 구간을 확인하세요.");
        try {
            Instant before = now();
            if (to.isAfter(before)) throw new ApiException(ErrorCode.VALIDATION_ERROR, "종료된 구간만 내보낼 수 있습니다.");
            long[] eventBudget = budget("SELECT payload FROM market_stream_events WHERE stock_code=? AND market_at>=? AND market_at<? LIMIT 10001",
                stock, LocalDateTime.ofInstant(from, ZoneOffset.UTC), LocalDateTime.ofInstant(to, ZoneOffset.UTC));
            long[] versionBudget = budget("SELECT payload FROM research_versions WHERE stock_code=? AND observed_at<? LIMIT 10001",
                stock, LocalDateTime.ofInstant(to, ZoneOffset.UTC));
            if (eventBudget[0] > MAX_ROWS || versionBudget[0] > MAX_ROWS || eventBudget[1] + versionBudget[1] > 32L * 1024 * 1024)
                throw new ApiException(ErrorCode.VALIDATION_ERROR, "내보내기 상한을 초과했습니다. 일부 자료로 완료 처리하지 않습니다.");
            var events = jdbc.query("SELECT event_id,stock_code,event_type,market_at,received_at,payload FROM market_stream_events "
                + "WHERE stock_code=? AND market_at>=? AND market_at<? ORDER BY market_at,event_id LIMIT 10001",
                (r, n) -> new StreamRow(r.getString(1), r.getString(2), r.getString(3),
                    r.getObject(4, LocalDateTime.class).toInstant(ZoneOffset.UTC),
                    r.getObject(5, LocalDateTime.class).toInstant(ZoneOffset.UTC), r.getString(6), ContentHash.sha256(r.getString(6))),
                stock, LocalDateTime.ofInstant(from, ZoneOffset.UTC), LocalDateTime.ofInstant(to, ZoneOffset.UTC));
            var versions = jdbc.query("SELECT change_id,kind,provider,stock_code,item_key,revision,observed_at,origin,payload,content_hash "
                + "FROM research_versions WHERE stock_code=? AND observed_at<? ORDER BY change_id LIMIT 10001",
                (r, n) -> new VersionRow(r.getLong(1), r.getString(2), r.getString(3), r.getString(4), r.getString(5),
                    r.getLong(6), r.getObject(7, LocalDateTime.class).toInstant(ZoneOffset.UTC), r.getString(8), r.getString(9), r.getString(10)),
                stock, LocalDateTime.ofInstant(to, ZoneOffset.UTC));
            if (events.size() > MAX_ROWS || versions.size() > MAX_ROWS)
                throw new ApiException(ErrorCode.VALIDATION_ERROR, "내보내기 상한을 초과했습니다. 일부 자료로 완료 처리하지 않습니다.");
            long bytes = 0;
            for (var row : events) {
                var value = json.readValue(row.payloadJson(), MarketStreamEvent.class);
                if (!row.eventId().equals(value.eventId()) || !stock.equals(value.stockCode()) || !row.type().equals(value.type())
                    || !row.marketAt().equals(value.marketTime().truncatedTo(ChronoUnit.MICROS))
                    || Duration.between(row.receivedAt(), value.receivedAt()).abs().toNanos() >= 1000) throw new IllegalStateException();
                bytes += row.payloadJson().getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
            }
            for (var row : versions) {
                if (!ContentHash.sha256(row.payloadJson()).equals(row.contentHash()) || row.revision() < 1) throw new IllegalStateException();
                if ("NEWS".equals(row.kind())) {
                    var value = json.readValue(row.payloadJson(), NewsArticle.class);
                    if (!stock.equals(value.stockCode()) || !row.provider().equals(value.provider())) throw new IllegalStateException();
                } else if ("DISCLOSURE".equals(row.kind())) {
                    var value = json.readValue(row.payloadJson(), Disclosure.class);
                    if (!stock.equals(value.stockCode()) || !row.provider().equals(value.provider())) throw new IllegalStateException();
                } else throw new IllegalStateException();
                bytes += row.payloadJson().getBytes(java.nio.charset.StandardCharsets.UTF_8).length;
            }
            if (bytes > 32L * 1024 * 1024) throw new ApiException(ErrorCode.VALIDATION_ERROR, "내보내기 용량 상한을 초과했습니다.");
            return new Snapshot("SAGOPALGO_STORED_EXPORT_V1", stock, from, to, now(), true, false,
                "REPEATABLE_READ", "OBSERVED_ONLY", "ALL_VERSIONS_OBSERVED_BEFORE_TO", List.copyOf(events), List.copyOf(versions));
        } catch (ApiException e) { throw e; }
        catch (Exception e) { throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR, "저장 자료의 025·026 적용 상태와 무결성을 확인하세요."); }
    }
    private Instant now() {
        return Objects.requireNonNull(jdbc.queryForObject("SELECT UTC_TIMESTAMP(6)", LocalDateTime.class)).toInstant(ZoneOffset.UTC);
    }
    private long[] budget(String selection, Object... args) {
        return jdbc.queryForObject("SELECT COUNT(*),COALESCE(SUM(OCTET_LENGTH(payload)),0) FROM (" + selection + ") export_budget",
            (r, n) -> new long[]{r.getLong(1), r.getLong(2)}, args);
    }
}
