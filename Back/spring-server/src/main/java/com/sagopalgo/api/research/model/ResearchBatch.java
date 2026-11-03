package com.sagopalgo.api.research.model;

import java.util.List;

/** 완전성은 해당 검색 범위의 페이지 확인이며 공급자 전체 기사/공시 보증이 아닙니다. */
public record ResearchBatch<T>(List<T> items,int pagesRead,boolean complete,String reason) {
    public ResearchBatch {items=List.copyOf(items);}
}
