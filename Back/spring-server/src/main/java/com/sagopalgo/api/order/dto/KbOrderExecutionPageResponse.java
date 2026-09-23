package com.sagopalgo.api.order.dto;

import java.util.List;

public record KbOrderExecutionPageResponse(
    String orderDate,
    String executionClassification,
    String continuationFlag,
    String nextKey,
    List<KbOrderExecutionItemResponse> items
) {
}
