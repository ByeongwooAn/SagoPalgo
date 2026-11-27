package com.sagopalgo.api.papertrading.controller;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.config.PersonalModeProperties;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.OffsetDateTime;
import java.time.format.DateTimeParseException;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

/** Reads the published dashboard for the configured local paper-trading trial. */
@RestController
public class AutomatedPaperTradingController {

    private static final int MAX_SNAPSHOT_BYTES = 1024 * 1024;

    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final String runId;
    private final Path snapshotPath;

    @Autowired
    public AutomatedPaperTradingController(
        ObjectMapper objectMapper,
        PersonalModeProperties personal,
        @Value("${SAGOPALGO_PAPER_TRIAL_DIRECTORY:}") String directory,
        @Value("${SAGOPALGO_PAPER_TRIAL_ID:2026-11-27-000660}") String runId
    ) {
        this(objectMapper, personal, directory, runId, Clock.systemUTC());
    }

    AutomatedPaperTradingController(
        ObjectMapper objectMapper, PersonalModeProperties personal, String directory, String runId, Clock clock
    ) {
        this.objectMapper = objectMapper;
        this.clock = clock;
        this.runId = runId;
        this.snapshotPath = personal.enabled() && !directory.isBlank() && runId.matches("[a-z0-9]+(?:-[a-z0-9]+)*")
            ? Path.of(directory).resolve(runId).resolve("dashboard.json") : null;
    }

    @GetMapping("/api/v1/paper-trading/automated")
    public ResponseEntity<ApiResponse<DashboardResponse>> getDashboard() {
        return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
            readDashboard(), "자동 모의매매 현황을 조회했습니다."
        ));
    }

    private DashboardResponse readDashboard() {
        if (snapshotPath == null) {
            return DashboardResponse.unavailable();
        }
        try (var file = Files.newInputStream(snapshotPath)) {
            byte[] bytes = file.readNBytes(MAX_SNAPSHOT_BYTES + 1);
            if (bytes.length > MAX_SNAPSHOT_BYTES) {
                return DashboardResponse.unavailable();
            }
            JsonNode snapshot = objectMapper.readTree(bytes);
            if (snapshot == null || snapshot.path("schemaVersion").asInt() != 1
                || !runId.equals(snapshot.path("runId").asText())
                || !snapshot.path("entry").isObject() || !snapshot.path("portfolio").isObject()
                || !snapshot.path("fills").isArray() || !snapshot.path("closedDays").isArray()) {
                return DashboardResponse.unavailable();
            }
            Instant published = OffsetDateTime.parse(snapshot.path("publishedAt").asText()).toInstant();
            Instant current = clock.instant();
            boolean online = !published.isAfter(current.plusSeconds(5)) && !published.isBefore(current.minusSeconds(120));
            return new DashboardResponse(true, online, snapshot);
        } catch (IOException | DateTimeParseException exception) {
            return DashboardResponse.unavailable();
        }
    }

    public record DashboardResponse(boolean available, boolean online, JsonNode snapshot) {
        static DashboardResponse unavailable() {
            return new DashboardResponse(false, false, null);
        }
    }
}
