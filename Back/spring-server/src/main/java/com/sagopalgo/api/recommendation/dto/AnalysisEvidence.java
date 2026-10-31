package com.sagopalgo.api.recommendation.dto;

/** 저장 당시의 분석 모델과 실제 입력 건수. 현재 뉴스/시세의 상태와는 구분합니다. */
public record AnalysisEvidence(String modelVersion, Integer candleCount, Integer newsCount, Integer disclosureCount) {}
