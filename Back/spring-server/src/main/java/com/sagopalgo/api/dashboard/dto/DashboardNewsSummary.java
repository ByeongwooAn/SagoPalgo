package com.sagopalgo.api.dashboard.dto;

import java.time.Instant;

public record DashboardNewsSummary(String status, String label, String method,
    int articleCount, int positiveCount, int negativeCount, Instant latestPublishedAt) {}
