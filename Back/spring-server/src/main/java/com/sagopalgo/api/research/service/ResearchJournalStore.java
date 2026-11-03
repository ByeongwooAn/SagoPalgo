package com.sagopalgo.api.research.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.config.ResearchProviderProperties;
import com.sagopalgo.api.research.mapper.ResearchJournalMapper;
import com.sagopalgo.api.research.model.*;
import java.util.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ResearchJournalStore {
    private final ResearchJournalMapper mapper;
    private final ObjectMapper json;
    private final ResearchProviderProperties policy;
    public ResearchJournalStore(ResearchJournalMapper mapper,ObjectMapper json,ResearchProviderProperties policy) {
        this.mapper=mapper;
        this.json=json.copy().setSerializationInclusion(com.fasterxml.jackson.annotation.JsonInclude.Include.ALWAYS)
            .disable(com.fasterxml.jackson.databind.SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        this.policy=policy;
    }
    public boolean enabled() {return policy.getIncremental().isEnabled();}
    public void verify() {if(mapper.verify()!=1) throw new IllegalStateException("RESEARCH_026_REQUIRED");}
    /** 전체 저장 트랜잭션의 첫 잠금. 커밋 순서와 change_id 순서를 일치시킵니다. */
    public void begin() {
        if(!TransactionSynchronizationManager.isActualTransactionActive()) throw new IllegalStateException("RESEARCH_TRANSACTION_REQUIRED");
        if(mapper.lockClock()==null) throw new IllegalStateException("RESEARCH_026_REQUIRED");
    }
    public ResearchRequest scope(String provider,ResearchRequest request) {
        var through=mapper.loadCheckpoint(provider,request.stockCode(),scopeKey(provider,request));
        if(through==null || through.isAfter(request.toDate())) return request;
        var overlap=through.minusDays(policy.getIncremental().getOverlapDays());
        // 장기간 중단 때 기본 lookback으로 오래된 미수집 구간을 조용히 건너뛰지 않습니다.
        return new ResearchRequest(request.stockCode(),request.stockName(),overlap,request.toDate());
    }
    public ResearchJournalMapper.Coverage coverage(String provider,ResearchRequest request) {
        return new ResearchJournalMapper.Coverage(provider,request.stockCode(),scopeKey(provider,request),request.toDate());
    }
    private String scopeKey(String provider,ResearchRequest request) {return hash(provider+"|"+request.stockCode()+"|"+request.stockName());}
    public void news(NewsArticle old,NewsArticle value,String key) {
        if(old!=null) append("NEWS",old.provider(),old.stockCode(),key,old,"LEGACY_BASELINE");
        append("NEWS",value.provider(),value.stockCode(),key,value,"OBSERVED");
    }
    public void disclosure(Disclosure old,Disclosure value) {
        String key=hash(value.provider()+"|"+value.stockCode()+"|"+value.receiptNumber());
        if(old!=null) append("DISCLOSURE",old.provider(),old.stockCode(),key,old,"LEGACY_BASELINE");
        append("DISCLOSURE",value.provider(),value.stockCode(),key,value,"OBSERVED");
    }
    private void append(String kind,String provider,String stock,String key,Object value,String origin) {
        String payload;
        try {payload=json.writeValueAsString(value);}catch(Exception e) {throw new IllegalStateException("RESEARCH_SERIALIZATION_FAILED");}
        String hash=hash(payload);
        mapper.seed(kind,provider,stock,key);var head=mapper.head(kind,provider,stock,key);
        if(hash.equals(head.hash())) return;
        long change=Objects.requireNonNull(mapper.lockClock())+1;
        mapper.advance(change);long revision=head.revision()+1;
        mapper.insert(new ResearchJournalMapper.Version(change,kind,provider,stock,key,revision,hash,payload,null,origin));
        mapper.update(kind,provider,stock,key,revision,hash);
    }
    public void checkpoint(List<ResearchJournalMapper.Coverage> coverage) {coverage.forEach(mapper::saveCheckpoint);}
    @Transactional(readOnly=true)
    public List<ResearchJournalMapper.Version> changes(String stock,long after,int limit) {return mapper.changes(stock,after,limit);}
    private String hash(String text) {return com.sagopalgo.api.common.util.ContentHash.sha256(text);}
}
