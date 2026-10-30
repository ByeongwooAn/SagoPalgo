package com.sagopalgo.api.kb.dto;

import java.time.Instant;

public record KbPortfolioImportResponse(
    boolean capitalImported, int createdCount, int updatedCount, int skippedCount, Instant importedAt
) {}
