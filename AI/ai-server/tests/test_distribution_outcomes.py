import json

import pytest

from app.replay.corporate_facts import as_of, audit, derive, extract
from app.replay.dart_documents import capture_document
from app.replay.dart_history import collect, prepare
from app.replay.distribution_facts import decimal, extract_distribution, parse_html, related_links
from app.replay.local_use import bind_local_use
from app.replay.models import ResearchError
from app.replay.related_documents import audit_related, capture_related
from app.replay.treasury_outcomes import derive_result, main, parse_result, reconcile
from test_corporate_facts import fixture as plan_fixture
from test_dart_documents import DocumentTransport, archive
from test_dart_history import FakeTransport
from test_history import FakeTransport as PriceTransport, collect as collect_prices, job as price_job

COMPANY = "가상회사"
DIVIDEND = "현금ㆍ현물 배당 결정"
CANCEL = "주식 소각 결정"
RESULT = "20240104000999"
DECISION = "20240102000000"
CANCELLATION = "20240102000100"
DIVIDEND_ID = "20240102000001"


def row(label, value):
    return f"<tr><td>{label}</td><td>{value}</td></tr>"


def pair(label, common, other, unit=""):
    return f'<tr><td rowspan="2">{label}</td><td>보통주식{unit}</td><td>{common}</td></tr><tr><td>종류주식{unit}</td><td>{other}</td></tr>'


def page(title, date, rows):
    return (f'<html><head><meta charset="utf-8"><title>{COMPANY}/{title}/({date.replace("-", ".")}){title}</title></head><body>'
            f'<table id="XFormD1_Form0_Table0"><tbody>{rows}</tbody></table></body></html>').encode()


def dividend():
    return page(DIVIDEND, "2024-01-02", row("2. 배당종류", "현금배당")
                + pair("3. 1주당 배당금(원)", "10.5", "11.5") + pair("4. 시가배당율(%)", "0.1", "0.2")
                + row("5. 배당금총액(원)", "10,000") + row("6. 배당기준일", "2023-12-31")
                + row("7. 배당금지급 예정일자", "-") + row("9. 주주총회 예정일자", "-")
                + row("10. 이사회결의일(결정일)", "2024-01-02"))


def href(receipt, label):
    return f'<a href="http://kind.krx.co.kr/common/disclsviewer.do?method=search&amp;acptno=20990101999999&amp;rcpno={receipt}&amp;orgid=F&amp;tran=Y&amp;langTpCd=0">{label}</a>'


def cancellation(common="1,000"):
    rows = pair("1. 소각할 주식의 종류와 수", common, "100", " (주)") + pair("2. 발행주식 총수", "5,000", "500", " (주)")
    rows += row("3. 1주당 가액(원)", "100") + row("4. 소각예정금액(원)", "110,000")
    rows += '<tr><td rowspan="2">5. 소각을 위한 자기주식 취득 예정기간</td><td>시작일</td><td>-</td></tr><tr><td>종료일</td><td>-</td></tr>'
    rows += row("7. 소각 예정일", "2024-01-06") + row("9. 이사회결의일(결정일)", "2024-01-05")
    rows += row("※관련공시", href(RESULT, "2024-01-04 자기주식취득결과보고서") + href(DECISION, "2024-01-02 자기주식 취득 결정"))
    return page(CANCEL, "2024-01-05", rows)


def selected(title=DIVIDEND):
    return {"reportName": title, "receiptDate": "2024-01-02" if title == DIVIDEND else "2024-01-05", "correctionIndicated": False, "withdrawalIndicated": False}


def result_fixture(entries=None):
    entries = entries or [("20240103", "6", 700, 600, 60000, "00000001"), ("20240104", "6", 400, 400, 40000, "00000001"),
                          ("20240103", "7", 60, 50, 5000, "00000002"), ("20240104", "7", 50, 50, 5000, "00000002")]
    rows = ""
    for date, cls, orders, actual, amount, broker in entries:
        shown = f"{date[:4]}년 {date[4:6]}월 {date[6:]}일"
        rows += (f'<TR><TU AUNIT="ACT_DT" AUNITVALUE="{date}">{shown}</TU><TU AUNIT="STK_KND" AUNITVALUE="{cls}">{"보통주식" if cls == "6" else "기타주식"}</TU>'
                 f'<TE ACODE="ORD_CNT">{orders}</TE><TE ACODE="ACT_CNT">{actual}</TE><TE ACODE="PCQ_AMT">{amount}</TE>'
                 f'<TE ACODE="UNIT_PRICE">99</TE><TE ACODE="CNS_CRP">{broker}</TE></TR>')
    sums = {code: sum(v[index] for v in entries) for code, index in [("SUM_ORD_CNT", 2), ("SUM_ACT_CNT", 3), ("ACQ_AMT", 4)]}
    return ('<DOCUMENT><DOCUMENT-NAME ACODE="00681">자기주식취득결과보고서</DOCUMENT-NAME><FORMULA-VERSION>6.0</FORMULA-VERSION>'
            '<COMPANY-NAME AREGCIK="00126380">가상회사</COMPANY-NAME><TABLE-GROUP ACLASS="ACT_BGN_DT">'
            '<TU AUNIT="ACT_BGN_DT" AUNITVALUE="20240103">2024년 01월 03일</TU><TU AUNIT="ACT_END_DT" AUNITVALUE="20240104">2024년 01월 04일</TU>'
            '</TABLE-GROUP><TABLE-GROUP ACLASS="ACT_DT"><TABLE>' + rows + '<TR>'
            + ''.join(f'<TE ACODE="{code}">{number}</TE>' for code, number in sums.items()) + '</TR></TABLE></TABLE-GROUP></DOCUMENT>').encode()


def sources(tmp_path):
    prices = tmp_path / "prices"
    prices.mkdir()
    history, _ = price_job(prices, startDate="2024-01-01", endDate="2024-01-10")
    collect_prices(history, PriceTransport(), sleeper=lambda _: None)
    profile = tmp_path / "scope.json"
    bind_local_use(history, profile)
    index = tmp_path / "index"
    prepare(history, profile, "00126380", index)
    def change(endpoint, params, value):
        if endpoint == "company": value.update(stock_name=COMPANY, corp_name=COMPANY)
        elif params["pblntf_ty"] == "B":
            if params["page_no"] == "1":
                value["list"][0]["report_nm"] = "[기재정정]주요사항보고서(자기주식 취득 결정)"
                value["list"][1]["report_nm"] = DIVIDEND
            else:
                value["list"][0].update(report_nm=CANCEL, rcept_dt="20240105")
    collect(index, FakeTransport(change=change), sleeper=lambda _: None)
    captured = {}
    for receipt, body in [(DECISION, plan_fixture()), (DIVIDEND_ID, dividend()), (CANCELLATION, cancellation())]:
        output = tmp_path / receipt
        capture_document(index, receipt, output, DocumentTransport(archive(body=body)))
        captured[receipt] = output
    result = tmp_path / "result"
    client = DocumentTransport(archive(body=result_fixture()))
    capture_related(index, captured[CANCELLATION], RESULT, result, client)
    return index, captured, result, client


def test_dividend_record_date_before_decision_and_unknown_payment_are_distinct():
    value = extract_distribution(dividend(), selected(), [COMPANY])
    dates = {v["role"]: v["value"] for v in value["dates"]}
    assert dates["RECORD_DATE"] < dates["DECISION_DATE"] and dates["PAYMENT_PLANNED_DATE"] is None
    assert value["numbers"][0]["value"] == "10.5" and value["numbers"][2]["unit"] == "PERCENT"
    assert value["unconfirmedDateRoles"] == ["EX_DATE", "ACTUAL_PAYMENT_DATE"]


def test_cancellation_keeps_reported_issued_shares_and_explicit_rcpno_link():
    value = extract_distribution(cancellation(), selected(CANCEL), [COMPANY])
    assert value["kind"] == "SHARE_CANCELLATION_PLAN" and value["numbers"][2]["role"] == "REPORTED_ISSUED_SHARES"
    assert sum(v["value"] is None for v in value["dates"]) == 2
    assert value["relatedDocuments"][0]["receiptNumber"] == RESULT
    assert value["relatedDocuments"][0]["receiptNumber"] != "20990101999999"


@pytest.mark.parametrize("value", ["1,00", "1e3", "-1", "01", "1.123456789"])
def test_decimal_formats_are_not_coerced(value):
    with pytest.raises(ResearchError): decimal(value)


@pytest.mark.parametrize("body,title,names", [
    (dividend().replace(COMPANY.encode(), b"other"), DIVIDEND, [COMPANY]),
    (dividend().replace(b'(2024.01.02)', b'(2024.01.03)'), DIVIDEND, [COMPANY]),
    (dividend().replace('현금배당'.encode(), '주식배당'.encode()), DIVIDEND, [COMPANY]),
    (dividend().replace(b'rowspan="2"', b'rowspan="1"'), DIVIDEND, [COMPANY]),
    (dividend().replace('종류주식'.encode(), '보통주식'.encode()), DIVIDEND, [COMPANY]),
    (cancellation("6,000"), CANCEL, [COMPANY]),
    (cancellation().replace(b'2024-01-06', b'2024-01-04'), CANCEL, [COMPANY]),
], ids=["issuer", "filing-date", "stock-dividend", "rowspan", "share-class", "too-many-cancelled", "date-role"])
def test_bad_or_unsupported_html_never_fills_facts(body, title, names):
    with pytest.raises(ResearchError): extract_distribution(body, selected(title), names)


@pytest.mark.parametrize("body", [b'<!DOCTYPE html><html></html>', b'<html><table></html>',
                                  dividend().replace(b' id="XFormD1_Form0_Table0"', b' id="unknown"')])
def test_html_declarations_structural_errors_and_unreviewed_table_are_rejected(body):
    with pytest.raises(ResearchError): extract_distribution(body, selected(), [COMPANY])


@pytest.mark.parametrize("mutation", [lambda s:s.replace(b'kind.krx.co.kr', b'kind.krx.co.kr.evil.example'),
                                     lambda s:s.replace(RESULT.encode(), (RESULT+'&amp;rcpno=123').encode()),
                                     lambda s:s.replace(b'2024-01-04 ', b'unknown-date ')])
def test_related_link_host_duplicate_parameter_or_unknown_date_is_rejected(mutation):
    with pytest.raises(ResearchError): related_links(parse_html(mutation(cancellation())))


def test_outcome_sums_actual_not_ordered_quantities_or_rounded_unit_price():
    value = parse_result(result_fixture(), "00126380")
    assert len(value["reportedRows"]) == 4 and value["totalsByShareClass"]["COMMON"]["shares"] == "1000"
    assert value["totalsByShareClass"]["COMMON"]["orders"] == "1100"
    assert value["totalsByShareClass"]["COMMON"]["amount"] == "100000" and not value["roundedUnitPriceUsedForAmount"]


@pytest.mark.parametrize("old,new", [(b'<TE ACODE="SUM_ACT_CNT">1100', b'<TE ACODE="SUM_ACT_CNT">1101'),
                                    (b'ACODE="00681"',b'ACODE="other"'),(b'AREGCIK="00126380"',b'AREGCIK="99999999"'),
                                    (b'AUNITVALUE="6"',b'AUNITVALUE="8"'),(b'<TE ACODE="ACT_CNT">600',b'<TE ACODE="ACT_CNT">800')],
                         ids=["totals", "form", "issuer", "class", "actual-exceeds-order"])
def test_outcome_must_reconcile_form_issuer_class_row_and_footer(old,new):
    with pytest.raises(ResearchError): parse_result(result_fixture().replace(old,new), "00126380")


def test_source_bound_html_extraction_preserves_old_xml_and_no_automatic_effect(tmp_path):
    index, captured, _, _ = sources(tmp_path)
    target = tmp_path / "dividend-facts.json"
    value = extract(index, captured[DIVIDEND_ID], target)
    assert audit(index, captured[DIVIDEND_ID], target) == value
    assert as_of(value, "2024-01-02T15:30:00+09:00")["facts"] == []
    assert derive(index, captured[DECISION])["kind"] == "TREASURY_ACQUISITION_PLAN"
    assert not value["automaticEffectAllowed"] and value["effectiveDate"] is None


def test_explicit_related_result_capture_cache_and_three_document_reconciliation(tmp_path):
    index, captured, result, client = sources(tmp_path)
    origin = captured[CANCELLATION]
    assert client.calls == [("document", {"rcept_no": RESULT})]
    metadata = audit_related(index, origin, result)
    assert capture_related(index, origin, RESULT, result, object()) == (metadata, True)
    facts = derive_result(index, origin, result)
    assert facts["stage"] == "REPORTED_OUTCOME" and facts["actualAcquisitionReported"]
    report = reconcile(index, origin, result, captured[DECISION])
    assert all(v["plannedQuantityFullyReported"] for v in report["comparisons"])
    assert not report["cancellationCompletionReported"] and not report["automaticEffectAllowed"]
    assert len(client.calls) == 1


def test_unlinked_receipt_cannot_trigger_any_request(tmp_path):
    index, captured, _, _ = sources(tmp_path)
    client = DocumentTransport()
    with pytest.raises(ResearchError): capture_related(index, captured[CANCELLATION], '20240104999999', tmp_path/'bad', client)
    assert not client.calls and not (tmp_path/'bad').exists()


def test_related_original_tampering_and_failed_reservation_are_preserved(tmp_path):
    index, captured, result, _ = sources(tmp_path)
    (result/'original.zip').write_bytes(b'changed')
    with pytest.raises(ResearchError): audit_related(index, captured[CANCELLATION], result)
    client = DocumentTransport(b'not a zip')
    output = tmp_path/'failed'
    with pytest.raises(ResearchError): capture_related(index, captured[CANCELLATION], RESULT, output, client)
    with pytest.raises(ResearchError): capture_related(index, captured[CANCELLATION], RESULT, output, client)
    assert len(client.calls) == 1
    (output/'capture.json').write_bytes(b'[]')
    with pytest.raises(ResearchError): capture_related(index, captured[CANCELLATION], RESULT, output, client)
    assert len(client.calls) == 1


def test_outcome_cli_audit_is_offline_and_never_confirms_cancellation(tmp_path, monkeypatch, capsys):
    index, captured, result, _ = sources(tmp_path)
    monkeypatch.delenv('SAGOPALGO_OPEN_DART_API_KEY', raising=False)
    facts = tmp_path/'outcome.json'
    args = ['--index',str(index),'--origin',str(captured[CANCELLATION]),'--capture',str(result)]
    assert main(['extract',*args,'--output',str(facts)]) == 0
    assert not json.loads(capsys.readouterr().out)['cancellationCompletionReported']
    assert main(['audit',*args,'--facts',str(facts)]) == 0
    assert json.loads(capsys.readouterr().out)['actualAcquisitionReported']
    assert main(['as-of',*args,'--facts',str(facts),'--at','2024-01-05T15:30:00+09:00']) == 0
    assert json.loads(capsys.readouterr().out)['visibleFacts'] == 0
    value = json.loads(facts.read_bytes())
    assert len(as_of(value, value['knownAt'])['facts']) == 1
    linked = tmp_path/'reconciliation.json'
    assert main(['reconcile',*args,'--decision',str(captured[DECISION]),'--output',str(linked)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary['reconciledShareClasses'] == 2 and 'reportedRows' not in summary
