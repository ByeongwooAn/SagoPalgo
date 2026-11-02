package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.config.SecuritiesProviderProperties;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.*;
import com.sagopalgo.api.kb.model.AccountObservationRecord;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.*;

public final class AccountObservationFixtures {
    public static final String DATE = "20261102";
    public static final LocalDateTime NOW = LocalDateTime.parse("2026-11-02T01:00:00.123456");
    private AccountObservationFixtures() {}

    public static SecuritiesProviderProperties properties() {
        var properties = new SecuritiesProviderProperties();
        var kb = properties.getKb();
        kb.setBaseUrl("https://kb.test"); kb.setTokenPath("/oauth2/token");
        kb.setAppKey("private-key"); kb.setAppSecret("private-secret"); kb.setAccountEnabled(true);
        return properties;
    }

    public static KbAccountSnapshotResponse snapshot(Status status) {
        Instant now = Instant.parse("2026-11-02T01:00:00Z");
        Map<String,String> fields = new LinkedHashMap<>();
        fields.put("is_cd","005930"); fields.put("hld_q_p6","0.123456");
        fields.put("ordr_psbl_q_p6","0.000001"); fields.put("now_prc",null);
        var sources = List.of("SSQM1801","SSQM2932","SSQM2952","SSQM2341");
        List<Section> sections = new ArrayList<>();
        for (String source : sources) {
            sections.add(new Section(source, source.equals("SSQM2341") ? Map.of("orderDate",DATE) : Map.of(),
                status, status == Status.PARTIAL ? Completeness.UNKNOWN : Completeness.COMPLETE,
                now,now,null,1,source.equals("SSQM2952") ? 1 : 0,null,
                Collections.singletonMap("ordr_psbl_csh",null),
                source.equals("SSQM2952") ? List.of(new Row(Collections.unmodifiableMap(fields))) : List.of(), List.of()));
        }
        return new KbAccountSnapshotResponse("KB_ACCOUNT_OBSERVATION_V1",UUID.randomUUID().toString(),
            "KB","primary",now,now,status,false,false,List.copyOf(sections));
    }

    public static AccountObservationRecord pending(String request, String binding) {
        return new AccountObservationRecord(1L,1L,request,binding,DATE,"PENDING",null,null,null,null,null,NOW,null);
    }

    public static AccountObservationRecord completed(String request, String binding,
        KbAccountSnapshotResponse snapshot, AccountObservationCodec codec) {
        var encoded = codec.encode(snapshot,DATE);
        return new AccountObservationRecord(1L,1L,request,binding,DATE,"COMPLETED",snapshot.observationId(),
            snapshot.status().name(),encoded.payload(),encoded.sha256(),null,NOW,NOW);
    }
}
