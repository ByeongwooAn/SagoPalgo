import json

import pytest

from app.replay.corporate_facts import as_of, audit, derive, extract, extract_content, integer, main, parse_xml
from app.replay.dart_documents import capture_document
from app.replay.dart_history import collect
from app.replay.dataset import canonical
from app.replay.models import ResearchError
from test_dart_documents import DocumentTransport, archive
from test_dart_history import FakeTransport, job

TITLE = "주요사항보고서(자기주식 취득 결정)"


def dated(code, value, shown):
    return f'<TU AUNIT="{code}" AUNITVALUE="{value}">{shown}</TU>'


def fixture():
    return (f'<DOCUMENT><DOCUMENT-NAME ACODE="11332">{TITLE}</DOCUMENT-NAME>'
            '<FORMULA-VERSION>1.5</FORMULA-VERSION><COMPANY-NAME AREGCIK="00126380">가상 회사</COMPANY-NAME>'
            '<CORRECTION><P>최초제출일 : 2024년 01월 02일</P><TABLE><TR><TH>가상 정정</TH></TR>'
            '<TR><TD>10. 1일 매수 주문수량 한도</TD><TD>가상 사유</TD><TD>기타주식: 12</TD><TD>기타주식: 11</TD></TR>'
            '<TR><TD>기타 참고</TD><TD>가상 사유</TD><TD>전 문장</TD><TD>후 문장</TD></TR></TABLE></CORRECTION>'
            '<TABLE-GROUP ACLASS="TBL_ACQ_STK"><TABLE>'
            '<TE ACODE="ACQ_OSTK">1,000</TE><TE ACODE="ACQ_ESTK">100</TE>'
            '<TE ACODE="ACQ_OSTK_PRC">2,000,000</TE><TE ACODE="ACQ_ESTK_PRC">300,000</TE>'
            '<TE ACODE="BUY_OSTK_LMT">110</TE><TE ACODE="BUY_ESTK_LMT">11</TE>'
            + dated("ACQ_DATE", "20240101", "2024년 01월 01일")
            + dated("ACQ_BGN", "20240103", "2024년 01월 03일")
            + dated("ACQ_END", "20240104", "2024년 01월 04일")
            + '<TE ACODE="ACQ_MTH">유가증권시장을 통한 장내 매수</TE><P>가상 브로커 A & B</P>'
            '</TABLE></TABLE-GROUP><TABLE-GROUP ACLASS="UNRELATED"><TE ACODE="ACQ_OSTK">999</TE></TABLE-GROUP></DOCUMENT>').encode()


def selected():
    return {"receiptNumber": "20240102000000", "receiptDate": "2024-01-02", "reportName": "[기재정정]" + TITLE,
            "correctionIndicated": True, "withdrawalIndicated": False}


def overseas_fixture():
    return ('<DOCUMENT><DOCUMENT-NAME ACODE="11314">주요사항보고서(해외 증권시장 주권등 상장폐지 결정)</DOCUMENT-NAME>'
            '<FORMULA-VERSION>1.3</FORMULA-VERSION><COMPANY-NAME AREGCIK="00126380">가상 회사</COMPANY-NAME>'
            '<TABLE-GROUP ACLASS="TBL1"><TE ACODE="DEL_CST_CNT">-</TE><TE ACODE="DEL_PST_CNT">2,500</TE>'
            '<TE ACODE="LST_MKT">가상 해외 거래소</TE>'
            + dated("DRC_DT", "20240101", "2024년 01월 01일")
            + dated("APP_DT", "20240103", "2024년 01월 03일")
            + dated("DELS_EXP_DT", "20240301", "2024년 03월 01일")
            + '</TABLE-GROUP><P>원주:DR=25:1, 다른 날짜 1991년 1월 1일</P></DOCUMENT>').encode()


def test_scoped_fields_keep_share_class_money_unit_and_planned_date_roles():
    value = extract_content(fixture(), selected(), [], "00126380")
    assert value["kind"] == "TREASURY_ACQUISITION_PLAN"
    assert [(v["role"], v["value"]) for v in value["dates"]] == [("DECISION_DATE", "2024-01-01"), ("PLANNED_START", "2024-01-03"), ("PLANNED_END", "2024-01-04")]
    assert value["numbers"][0]["value"] == "1000" and value["numbers"][1]["unit"] == "KRW"
    assert value["numbers"][3]["shareClass"] == "OTHER"
    assert value["instrument"]["otherShareClassStockCode"] is None
    assert value["normalization"]["bareAmpersandEscapes"] == 1
    assert value["correction"]["changes"] == [{"role": "DAILY_ORDER_LIMIT", "shareClass": "OTHER", "before": "12", "after": "11", "mainFieldMatched": True}]
    assert value["correction"]["unparsedChangeRows"] == 1


def test_same_submission_date_is_only_a_parent_candidate_and_cannot_choose_intraday_order():
    row = selected()
    rows = [row, {**row, "receiptNumber": "20240102000001"}, {**row, "receiptNumber": "20240102000002"}]
    correction = extract_content(fixture(), row, rows, "00126380")["correction"]
    assert correction["chainStatus"] == "AMBIGUOUS" and correction["directParentReceiptNumber"] is None
    assert len(correction["candidateReceiptNumbers"]) == 2
    one_parent = extract_content(fixture(), row, rows[:2], "00126380")["correction"]
    assert one_parent["chainStatus"] == "CANDIDATE_ONLY" and one_parent["directParentReceiptNumber"] is None


def test_foreign_plan_keeps_unknown_count_and_does_not_convert_dr_ratio_into_stock_split():
    row = {**selected(), "reportName": "주요사항보고서(해외증권시장주권등상장폐지결정)"}
    value = extract_content(overseas_fixture(), row, [], "00126380")
    assert value["kind"] == "OVERSEAS_DELISTING_PLAN" and value["instrument"]["scope"] == "OVERSEAS_SECURITIES"
    assert value["numbers"][0]["value"] is None and value["numbers"][1]["value"] == "2500"
    assert value["numbers"][1]["unit"] == "ISSUER_REPORTED_SHARES"
    assert value["dates"][2]["value"] == "2024-03-01" and "splitRatio" not in value


@pytest.mark.parametrize("number", ["1,00", "01", "1.5", "-1", "1e6", "1000000000000000000", "미확인"])
def test_invalid_numbers_are_not_coerced_or_rounded(number):
    with pytest.raises(ResearchError): integer(number)


@pytest.mark.parametrize("changed,code", [
    (lambda s: s.replace(b'AREGCIK="00126380"', b'AREGCIK="99999999"'), "ISSUER_MISMATCH"),
    (lambda s: s.replace(b'<FORMULA-VERSION>1.5', b'<FORMULA-VERSION>9.9'), "FORM_VERSION_UNSUPPORTED"),
    (lambda s: s.replace(b'<TE ACODE="ACQ_OSTK">1,000</TE>', b'<TE ACODE="ACQ_OSTK">1,000</TE><TE ACODE="ACQ_OSTK">2,000</TE>'), "FIELD_AMBIGUOUS"),
    (lambda s: s.replace(b'ACODE="ACQ_OSTK"', b'ACODE="MISSING"'), "FIELD_AMBIGUOUS"),
    (lambda s: s.replace('2024년 01월 03일'.encode(), '2024년 01월 05일'.encode()), "DATE_DISPLAY_CONFLICT"),
    (lambda s: s.replace(dated("ACQ_END", "20240104", "2024년 01월 04일").encode(), dated("ACQ_END", "20231231", "2023년 12월 31일").encode()), "DATE_ORDER_INVALID"),
    (lambda s: s.replace('기타주식: 11'.encode(), '기타주식: 10'.encode()), "CORRECTION_MAIN_CONFLICT"),
    (lambda s: s.replace('유가증권시장을 통한 장내 매수'.encode(), '다른 거래 경로'.encode()), "MARKET_METHOD_UNSUPPORTED"),
], ids=["issuer", "version", "duplicate", "missing", "date-display", "reversed-dates", "correction-main", "unsupported-market"])
def test_conflicting_or_unsupported_originals_fail_without_filling_fields(changed, code):
    with pytest.raises(ResearchError, match=code):
        extract_content(changed(fixture()), selected(), [], "00126380")


@pytest.mark.parametrize("payload", [b'<!DOCTYPE DOCUMENT SYSTEM "https://example.invalid/secret"><DOCUMENT/>',
                                     b'<!DOCTYPE DOCUMENT [<!ENTITY x "expansion">]><DOCUMENT>&x;</DOCUMENT>',
                                     b'<DOCUMENT><broken></DOCUMENT>'])
def test_external_or_internal_declarations_and_malformed_xml_are_rejected(payload):
    with pytest.raises(ResearchError): parse_xml(payload)


def test_unknown_dates_do_not_hide_reversed_known_end_date():
    body = fixture().replace(dated("ACQ_BGN", "20240103", "2024년 01월 03일").encode(), dated("ACQ_BGN", "-", "-").encode())
    body = body.replace(dated("ACQ_END", "20240104", "2024년 01월 04일").encode(), dated("ACQ_END", "20231231", "2023년 12월 31일").encode())
    with pytest.raises(ResearchError, match="DATE_ORDER_INVALID"):
        extract_content(body, selected(), [], "00126380")


def source(tmp_path):
    index = job(tmp_path)
    def change(endpoint, params, value):
        if endpoint == "list" and params["pblntf_ty"] == "B" and params["page_no"] == "1":
            value["list"][0]["report_nm"] = selected()["reportName"]
    collect(index, FakeTransport(change=change), sleeper=lambda _: None)
    capture = tmp_path / "original"
    capture_document(index, "20240102000000", capture, DocumentTransport(archive(body=fixture())))
    return index, capture


def test_extract_audit_and_asof_bind_sources_and_never_emit_effects(tmp_path):
    index, capture = source(tmp_path)
    originals = {(folder, name): (folder / name).read_bytes() for folder, names in [(index, ["report.json", "disclosures.jsonl", "journal.json"]), (capture, ["capture.json", "original.zip"])] for name in names}
    output = tmp_path / "facts.json"
    value = extract(index, capture, output)
    assert audit(index, capture, output) == value
    assert as_of(value, "2024-01-02T15:30:00+09:00")["facts"] == []
    assert as_of(value, value["knownAt"])["facts"] == [value]
    assert value["effectiveDate"] is None and not value["automaticEffectAllowed"] and value["referenceEventsEmitted"] == 0
    assert value["availability"] == "OBSERVED_AT" and value["stage"] == "DECLARED_PLAN"
    assert all((folder / name).read_bytes() == body for (folder, name), body in originals.items())
    with pytest.raises(FileExistsError): extract(index, capture, output)


def test_tampered_derived_facts_or_capture_binding_are_rejected(tmp_path):
    index, capture = source(tmp_path)
    path = tmp_path / "facts.json"
    value = extract(index, capture, path)
    value["automaticEffectAllowed"] = True
    with pytest.raises(ResearchError, match="SNAPSHOT_INVALID"): as_of(value, value["knownAt"])
    path.write_bytes(canonical(value))
    with pytest.raises(ResearchError, match="DERIVATION_TAMPERED"): audit(index, capture, path)
    original = json.loads((capture / "capture.json").read_bytes())
    original["indexInstrumentScope"] = "OVERSEAS_SECURITIES"
    (capture / "capture.json").write_bytes(canonical(original))
    with pytest.raises(ResearchError, match="SCOPE_CONFLICT"): derive(index, capture)


def test_cli_extract_and_asof_are_offline_and_report_readiness_separately(tmp_path, monkeypatch, capsys):
    index, capture = source(tmp_path)
    monkeypatch.delenv("SAGOPALGO_OPEN_DART_API_KEY", raising=False)
    facts = tmp_path / "facts.json"
    arguments = ["--index", str(index), "--capture", str(capture)]
    assert main(["extract", *arguments, "--output", str(facts)]) == 0
    assert json.loads(capsys.readouterr().out)["automaticEffectAllowed"] is False
    assert main(["as-of", *arguments, "--facts", str(facts), "--at", "2024-01-02T15:30:00+09:00"]) == 0
    assert json.loads(capsys.readouterr().out)["visibleFacts"] == 0
