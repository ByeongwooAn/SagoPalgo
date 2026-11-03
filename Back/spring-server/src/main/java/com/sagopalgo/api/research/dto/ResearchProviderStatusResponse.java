package com.sagopalgo.api.research.dto;

/**
 * 통합 조회 중 각 Provider가 실제로 어떻게 처리됐는지 알려줍니다.
 */
public record ResearchProviderStatusResponse(
    String provider,
    String dataType,
    String status,
    String message,
    Integer pagesRead,
    Boolean complete,
    java.time.LocalDate fromDate,
    java.time.LocalDate toDate
) {
    public ResearchProviderStatusResponse(String provider,String dataType,String status,String message) {
        this(provider,dataType,status,message,null,null,null,null);
    }
    public ResearchProviderStatusResponse(String provider,String dataType,String status,String message,Integer pagesRead,Boolean complete) {
        this(provider,dataType,status,message,pagesRead,complete,null,null);
    }
}
