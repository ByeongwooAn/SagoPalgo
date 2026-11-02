package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.*;
import java.time.Instant;
import java.util.*;
import java.util.function.UnaryOperator;

final class AccountObservationComparisonFixtures {
    private AccountObservationComparisonFixtures() {}

    static KbAccountSnapshotResponse observation(int minute) {
        Instant start = Instant.parse("2026-11-02T01:00:00Z").plusSeconds(60L*minute);
        var sources = List.of("SSQM1801","SSQM2932","SSQM2952","SSQM2341");
        List<Section> sections = new ArrayList<>();
        for (var source : sources) sections.add(new Section(source,
            source.equals("SSQM2341") ? Map.of("orderDate",AccountObservationFixtures.DATE,"executionClassification","0") : Map.of("basis",source),
            Status.SUCCESS,Completeness.COMPLETE,start,start.plusSeconds(1),null,1,0,0,Map.of(),List.of(),List.of()));
        return new KbAccountSnapshotResponse("KB_ACCOUNT_OBSERVATION_V1",UUID.randomUUID().toString(),"KB","primary",
            start,start.plusSeconds(1),Status.SUCCESS,false,false,List.copyOf(sections));
    }

    static KbAccountSnapshotResponse change(KbAccountSnapshotResponse snapshot, int index, UnaryOperator<Section> transform) {
        var sections = new ArrayList<>(snapshot.sections()); sections.set(index,transform.apply(sections.get(index)));
        return new KbAccountSnapshotResponse(snapshot.contractVersion(),snapshot.observationId(),snapshot.provider(),snapshot.accountAlias(),
            snapshot.startedAt(),snapshot.completedAt(),snapshot.status(),false,false,List.copyOf(sections));
    }

    static Section rows(Section s, Row... rows) {
        return new Section(s.api(),s.scope(),s.status(),s.completeness(),s.startedAt(),s.completedAt(),s.providerProcessTime(),
            s.pagesRead(),rows.length,rows.length,s.summary(),List.of(rows),s.issues());
    }

    static Section summary(Section s, Map<String,String> summary) {
        return new Section(s.api(),s.scope(),s.status(),s.completeness(),s.startedAt(),s.completedAt(),s.providerProcessTime(),
            s.pagesRead(),s.receivedRowCount(),s.reportedTotalCount(),summary,s.rows(),s.issues());
    }

    static Section scope(Section s, Map<String,String> scope) {
        return new Section(s.api(),scope,s.status(),s.completeness(),s.startedAt(),s.completedAt(),s.providerProcessTime(),
            s.pagesRead(),s.receivedRowCount(),s.reportedTotalCount(),s.summary(),s.rows(),s.issues());
    }

    static Row row(String... entries) {
        Map<String,String> fields = new LinkedHashMap<>();
        for (int i=0; i<entries.length; i+=2) fields.put(entries[i],entries[i+1]);
        return new Row(Collections.unmodifiableMap(fields));
    }

    static Row identified(int section, String value) {
        return switch (section) {
            case 0 -> row("is_no",value,"gnrl_q","0.123456");
            case 1 -> row("gds_typ","STOCK","clsf","A","crncy_cd","KRW","is_cd",value,
                "is_dtl_typ_cd","01","fnl_ccls_excg_cd","KRX","blnc_q_p6","0.123456");
            case 2 -> row("clsf","A","crncy_cd","KRW","is_cd",value,
                "is_dtl_typ_cd","01","fnl_ccls_excg_cd","KRX","hld_q_p6","0.123456");
            default -> row("ordr_no",value,"stnd_is_no","005930","nccls_q","1");
        };
    }

    static AccountObservationResponse response(KbAccountSnapshotResponse snapshot) {
        return new AccountObservationResponse(UUID.randomUUID().toString(),AccountObservationFixtures.DATE,"COMPLETED",
            snapshot.observationId(),snapshot.status().name(),snapshot.startedAt(),snapshot.completedAt(),null,true,snapshot);
    }
}
