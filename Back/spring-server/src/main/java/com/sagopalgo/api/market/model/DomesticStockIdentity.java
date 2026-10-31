package com.sagopalgo.api.market.model;

/** 코드만으로 조회한 국내 종목의 등록용 정보입니다. */
public record DomesticStockIdentity(String provider, String stockCode, String stockName, String market) { }
