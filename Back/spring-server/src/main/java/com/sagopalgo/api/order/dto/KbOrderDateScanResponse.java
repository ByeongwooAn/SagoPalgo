package com.sagopalgo.api.order.dto;

import java.util.List;

public record KbOrderDateScanResponse(
    String orderDate,
    boolean completeScan,
    int pagesScanned,
    boolean itemLimitReached,
    List<KbOrderExecutionItemResponse> items
) {
}
