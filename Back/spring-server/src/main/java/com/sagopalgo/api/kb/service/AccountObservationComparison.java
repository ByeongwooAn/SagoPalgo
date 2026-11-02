package com.sagopalgo.api.kb.service;

import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse;
import com.sagopalgo.api.kb.dto.AccountObservationComparisonResponse.*;
import com.sagopalgo.api.kb.dto.AccountObservationResponse;
import com.sagopalgo.api.kb.dto.KbAccountSnapshotResponse.*;
import java.math.BigDecimal;
import java.util.*;
import org.springframework.stereotype.Component;

/** 저장된 동일 연결 관찰의 순수 비교. 외부 조회·DB 쓰기·상태 반영에 의존하지 않습니다. */
@Component
public class AccountObservationComparison {
    private record Spec(String api, List<String> keys, List<String> text, List<String> numbers, List<String> summary) {
        Spec(String api, String keys, String text, String numbers, String summary) {
            this(api, words(keys), words(text), words(numbers), words(summary));
        }
        private static List<String> words(String value) { return value.isEmpty() ? List.of() : List.of(value.split(" ")); }
    }

    private static final List<Spec> SPECS = List.of(
        new Spec("SSQM1801", "is_no", "is_no is_nm", "gnrl_q ordr_psbl_q", "gnrl_q ordr_psbl_q"),
        new Spec("SSQM2932", "gds_typ clsf crncy_cd is_cd is_dtl_typ_cd fnl_ccls_excg_cd",
            "gds_typ clsf crncy_cd is_cd is_nm is_dtl_typ_cd fnl_ccls_excg_cd",
            "blnc_q blnc_q_p6 ordr_psbl_q ordr_psbl_q_p6 now_prc byng_avr_prc val_amt pl_amt yld val_sgrvt_p2",
            "tfnd o_amt_psbl_amt ordr_psbl_csh byng_amt_sum pl_amt_sum val_amt_sum yld_sum"),
        new Spec("SSQM2952", "clsf crncy_cd is_cd is_dtl_typ_cd fnl_ccls_excg_cd",
            "clsf crncy_cd is_cd is_nm is_dtl_typ_cd fnl_ccls_excg_cd",
            "hld_q hld_q_p6 ordr_psbl_q ordr_psbl_q_p6 nstmt_s_q nstmt_s_q_p6 nstmt_b_q nstmt_b_q_p6 ec_q ec_q_p6 byng_amt now_prc byng_avr_prc val_amt val_pl val_yld",
            "dy_tfnd ndy_tfnd nxt2_dy_tfnd nt_asts_val_amt scrts_nt_val_amt ndy_o_amt_psbl_amt byng_amt_sum val_amt_sum val_pl_sum val_yld_sum"),
        new Spec("SSQM2341", "ordr_no stnd_is_no",
            "orgn_ordr_no stnd_is_no ordr_no trd_dl_ccd_nm hngl_shrt_nm ordr_tm ordr_ccd crct_cncl_ccd sor_ordr_ccd",
            "ordr_q tl_ccls_q nccls_q ordr_uprc ccls_uprc crct_q sor_cncl_q", "s_ccls_amt b_ccls_amt s_ccls_q b_ccls_q")
    );

    public AccountObservationComparisonResponse compare(AccountObservationResponse before, AccountObservationResponse after) {
        boolean stored = before.observation() != null && after.observation() != null
            && "COMPLETED".equals(before.storageState()) && "COMPLETED".equals(after.storageState());
        boolean forward = stored && !before.observation().completedAt().isAfter(after.observation().startedAt());
        List<SectionComparison> sections = new ArrayList<>();
        for (int i=0; i<SPECS.size(); i++) {
            var left = before.observation() == null ? null : before.observation().sections().get(i);
            var right = after.observation() == null ? null : after.observation().sections().get(i);
            sections.add(section(SPECS.get(i), left, right,
                !stored ? Reason.STORAGE_NOT_COMPLETED : !forward ? Reason.INTERVAL_NOT_FORWARD : null));
        }
        long count = sections.stream().filter(s -> s.status() == ComparisonStatus.COMPARED).count();
        var status = count == 4 ? ComparisonStatus.COMPARED : count == 0 ? ComparisonStatus.BLOCKED : ComparisonStatus.PARTIAL;
        return new AccountObservationComparisonResponse("KB_ACCOUNT_COMPARISON_V1", reference(before), reference(after),
            status, true, false, List.copyOf(sections));
    }

    private SectionComparison section(Spec spec, Section before, Section after, Reason globalReason) {
        Set<Reason> reasons = new LinkedHashSet<>();
        if (globalReason != null) reasons.add(globalReason);
        if (before != null && after != null) {
            if (!before.scope().equals(after.scope())) reasons.add(Reason.SCOPE_MISMATCH);
            inspect(before,spec,reasons); inspect(after,spec,reasons);
        }
        if (!reasons.isEmpty()) return result(spec,before,after,reasons,List.of(),List.of());

        var left = index(before,spec); var right = index(after,spec);
        Set<RowKey> keys = new TreeSet<>(left.keySet()); keys.addAll(right.keySet());
        List<RowChange> changes = new ArrayList<>();
        List<String> fields = new ArrayList<>(spec.text()); fields.addAll(spec.numbers()); fields.removeAll(spec.keys());
        for (var key : keys) {
            var a = left.get(key); var b = right.get(key);
            var diffs = fields(a == null ? Map.of() : a, b == null ? Map.of() : b, fields, spec.numbers());
            // 한쪽에만 있는 행은 식별자 외 필드가 없어도 관찰 차이로 남깁니다.
            if (a == null || b == null || !diffs.isEmpty()) {
                Map<String,String> identity = new LinkedHashMap<>();
                for (int i=0; i<spec.keys().size(); i++) identity.put(spec.keys().get(i), key.values().get(i));
                changes.add(new RowChange(a == null ? RowChangeKind.OBSERVED_ONLY_AFTER
                    : b == null ? RowChangeKind.OBSERVED_ONLY_BEFORE : RowChangeKind.CHANGED,
                    Collections.unmodifiableMap(identity),diffs));
            }
        }
        return result(spec,before,after,reasons,fields(before.summary(),after.summary(),spec.summary(),spec.summary()),List.copyOf(changes));
    }

    private void inspect(Section section, Spec spec, Set<Reason> reasons) {
        if (section.status() != Status.SUCCESS) reasons.add(Reason.SECTION_UNAVAILABLE);
        if (section.completeness() != Completeness.COMPLETE) reasons.add(Reason.SECTION_INCOMPLETE);
        if (!section.issues().isEmpty()) reasons.add(Reason.SECTION_HAS_ISSUES);
        if (section.pagesRead() < 1 || section.receivedRowCount() != section.rows().size()
            || (section.reportedTotalCount() != null && section.reportedTotalCount() != section.rows().size())) {
            reasons.add(Reason.INVALID_ROW_COUNT);
        }
        if (!new HashSet<>(spec.summary()).containsAll(section.summary().keySet())) reasons.add(Reason.UNSUPPORTED_FIELDS);
        numeric(section.summary(),spec.summary(),reasons);
        Set<RowKey> seen = new HashSet<>();
        Set<String> allowed = new HashSet<>(spec.text()); allowed.addAll(spec.numbers());
        for (var row : section.rows()) {
            if (row == null || row.fields() == null) { reasons.add(Reason.INVALID_ROW_IDENTITY); continue; }
            var fields = row.fields();
            if (!allowed.containsAll(fields.keySet())) reasons.add(Reason.UNSUPPORTED_FIELDS);
            if (spec.keys().stream().anyMatch(k -> fields.get(k) == null || fields.get(k).isBlank())) {
                reasons.add(Reason.INVALID_ROW_IDENTITY);
            } else if (!seen.add(key(fields,spec))) reasons.add(Reason.DUPLICATE_ROW_IDENTITY);
            numeric(fields,spec.numbers(),reasons);
        }
    }

    private void numeric(Map<String,String> fields, List<String> numbers, Set<Reason> reasons) {
        for (String name : numbers) {
            String value = fields.get(name);
            if (value != null && (value.length() > 64 || !value.matches("[-+]?[0-9]+(?:\\.[0-9]+)?"))) {
                reasons.add(Reason.INVALID_NUMBER);
            }
        }
    }

    private List<FieldChange> fields(Map<String,String> before, Map<String,String> after, List<String> names, List<String> numbers) {
        List<FieldChange> result = new ArrayList<>();
        for (String name : names) {
            String a = before.get(name); String b = after.get(name);
            boolean numeric = numbers.contains(name);
            boolean equal = numeric && a != null && b != null ? new BigDecimal(a).compareTo(new BigDecimal(b)) == 0 : Objects.equals(a,b);
            if (before.containsKey(name) == after.containsKey(name) && equal) continue;
            String delta = numeric && a != null && b != null
                ? new BigDecimal(b).subtract(new BigDecimal(a)).stripTrailingZeros().toPlainString() : null;
            result.add(new FieldChange(name,before.containsKey(name),after.containsKey(name),a,b,delta));
        }
        return List.copyOf(result);
    }

    private record RowKey(List<String> values) implements Comparable<RowKey> {
        @Override public int compareTo(RowKey other) {
            for (int i=0; i<values.size(); i++) {
                int result = values.get(i).compareTo(other.values.get(i));
                if (result != 0) return result;
            }
            return 0;
        }
    }
    private RowKey key(Map<String,String> fields, Spec spec) { return new RowKey(spec.keys().stream().map(fields::get).toList()); }
    private Map<RowKey,Map<String,String>> index(Section section, Spec spec) {
        Map<RowKey,Map<String,String>> result = new TreeMap<>();
        for (var row : section.rows()) result.put(key(row.fields(),spec),row.fields());
        return result;
    }
    private SectionComparison result(Spec spec, Section a, Section b, Set<Reason> reasons,
        List<FieldChange> summary, List<RowChange> rows) {
        return new SectionComparison(spec.api(),a == null ? Map.of() : a.scope(),b == null ? Map.of() : b.scope(),
            info(a),info(b),reasons.isEmpty() ? ComparisonStatus.COMPARED : ComparisonStatus.BLOCKED,List.copyOf(reasons),summary,rows);
    }
    private SourceInfo info(Section value) {
        return value == null ? null : new SourceInfo(value.status(),value.completeness(),value.startedAt(),value.completedAt(),
            value.receivedRowCount(),value.reportedTotalCount(),value.issues());
    }
    private Reference reference(AccountObservationResponse value) {
        var observation = value.observation();
        return new Reference(value.requestId(),value.orderDate(),value.storageState(),value.observationId(),value.snapshotStatus(),
            value.failureCode(),observation == null ? null : observation.startedAt(),observation == null ? null : observation.completedAt());
    }
}
