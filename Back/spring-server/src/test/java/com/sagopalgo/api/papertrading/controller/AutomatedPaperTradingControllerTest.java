package com.sagopalgo.api.papertrading.controller;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.PersonalModeProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class AutomatedPaperTradingControllerTest {

    private static final String RUN = "2026-11-27-000660";
    private static final Clock CLOCK = Clock.fixed(Instant.parse("2026-11-27T09:00:30Z"), ZoneOffset.UTC);

    @TempDir Path directory;

    @Test
    void servesFreshSnapshotAndRetainsStaleLedgerForDisplay() throws Exception {
        var controller = controller(true, RUN);
        writeSnapshot("2026-11-27T18:00:00+09:00");
        var response = controller.getDashboard();
        assertThat(response.getHeaders().getCacheControl()).isEqualTo("no-store");
        assertThat(response.getBody().data().available()).isTrue();
        assertThat(response.getBody().data().online()).isTrue();
        assertThat(response.getBody().data().snapshot().path("runId").asText()).isEqualTo(RUN);

        writeSnapshot("2026-11-27T17:50:00+09:00");
        var stale = controller.getDashboard().getBody().data();
        assertThat(stale.available()).isTrue();
        assertThat(stale.online()).isFalse();
    }

    @Test
    void unavailableWhenMissingInvalidOrOutsidePersonalMode() throws Exception {
        assertThat(controller(true, RUN).getDashboard().getBody().data().available()).isFalse();
        writeSnapshot("not-a-time");
        assertThat(controller(true, RUN).getDashboard().getBody().data().available()).isFalse();
        writeSnapshot("2026-11-27T18:00:00+09:00");
        assertThat(controller(false, RUN).getDashboard().getBody().data().available()).isFalse();
        assertThat(controller(true, "../" + RUN).getDashboard().getBody().data().available()).isFalse();
    }

    private AutomatedPaperTradingController controller(boolean enabled, String run) {
        var personal = new PersonalModeProperties(enabled, 1L, "local", "local@example.com");
        return new AutomatedPaperTradingController(new ObjectMapper(), personal, directory.toString(), run, CLOCK);
    }

    private void writeSnapshot(String publishedAt) throws Exception {
        Path runDirectory = Files.createDirectories(directory.resolve(RUN));
        Files.writeString(runDirectory.resolve("dashboard.json"), """
            {"schemaVersion":1,"runId":"%s","publishedAt":"%s",
             "entry":{},"portfolio":{},"fills":[],"closedDays":[]}
            """.formatted(RUN, publishedAt));
    }
}
