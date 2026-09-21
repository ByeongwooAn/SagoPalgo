package com.sagopalgo.api.research.dto;

/**
 * 자동 동기화 설정과 선택 종목의 마지막 실행 상태입니다.
 */
public record ResearchSyncStatusResponse(
    boolean enabled,
    String cron,
    String zone,
    ResearchSyncStatusItemResponse item
) {
}
