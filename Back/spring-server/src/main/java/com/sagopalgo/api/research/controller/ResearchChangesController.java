package com.sagopalgo.api.research.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.sagopalgo.api.common.exception.*;
import com.sagopalgo.api.common.response.ApiResponse;
import com.sagopalgo.api.research.service.ResearchJournalStore;
import java.time.ZoneOffset;
import java.util.*;
import org.springframework.http.*;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/research/changes")
public class ResearchChangesController {
    private final ResearchJournalStore store;
    private final ObjectMapper json;
    public ResearchChangesController(ResearchJournalStore store,ObjectMapper json) {this.store=store;this.json=json;}
    @GetMapping public ResponseEntity<?> changes(@RequestParam String stockCode,@RequestParam(defaultValue="0") long afterId,
        @RequestParam(defaultValue="100") int limit) {
        if(stockCode==null || !stockCode.matches("[0-9]{6}") || afterId<0 || limit<1 || limit>100)
            throw new ApiException(ErrorCode.VALIDATION_ERROR,"변경 이력의 종목·커서를 확인하세요.");
        if(!store.enabled()) return ResponseEntity.ok().cacheControl(CacheControl.noStore())
            .body(ApiResponse.success(Map.of("enabled",false,"items",List.of(),"nextAfterId",afterId),"변경 이력 비활성"));
        try {
            var versions=store.changes(stockCode,afterId,limit);
            List<Object> items=new ArrayList<>();
            for(var v:versions) items.add(Map.of("changeId",v.changeId(),"kind",v.kind(),"provider",v.provider(),"stockCode",v.stockCode(),
                "itemKey",v.itemKey(),"revision",v.revision(),"observedAt",v.observedAt().toInstant(ZoneOffset.UTC),
                "origin",v.origin(),"content",json.readTree(v.payload())));
            return ResponseEntity.ok().cacheControl(CacheControl.noStore()).body(ApiResponse.success(
                Map.of("enabled",true,"items",items,"nextAfterId",versions.isEmpty()?afterId:versions.get(versions.size()-1).changeId()),"저장된 뉴스·공시 변경입니다."));
        } catch(Exception e) {throw new ApiException(ErrorCode.EXTERNAL_DATA_ERROR,"뉴스·공시 변경 저장소 026 적용 상태를 확인하세요.");}
    }
}
