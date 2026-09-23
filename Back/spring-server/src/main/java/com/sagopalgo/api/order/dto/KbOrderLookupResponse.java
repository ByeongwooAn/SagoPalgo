package com.sagopalgo.api.order.dto;

import java.util.List;

public record KbOrderLookupResponse(
    String orderDate,
    String orderNo,
    boolean completeScan,
    int pagesScanned,
    List<KbOrderExecutionItemResponse> matches
) {
}
