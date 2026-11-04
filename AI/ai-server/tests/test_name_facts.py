"""Name date roles, exact identities, conservative corporate markers and correction lineage."""
from copy import deepcopy
from pathlib import Path

import pytest

from app.replay import name_facts as facts, name_disclosures as acquisition
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from test_name_disclosures import planned, Client, RECEIPT, DOC, URL, search, viewer

AT = "2026-11-04T12:00:00Z"
LATER = "2026-11-04T13:00:00Z"


def body(before="(주)가상구명", after="가상신명 주식회사", stamp="2024-01-03", corrected=False):
    title = '<div class="xforms_title">정정신고(보고)</div>' if corrected else ''
    return (f'<html>{title}<div class="xforms_title">변경상장(상호변경)</div><table>'
            f'<tr><td>1.변경전 상호</td><td>{before}</td></tr>'
            '<tr><td>2.변경상장사유</td><td>상호변경</td></tr>'
            f'<tr><td>3.변경후 상호</td><td>정식명</td><td>한글</td><td>{after}</td></tr>'
            f'<tr><td>4.상장일</td><td>{stamp}</td></tr></table></html>').encode()


def target_context():
    target = {"observationId": "a" * 64, "symbol": "000010", "isin": "KR0000100001", "beforeMarket": "KOSDAQ", "afterMarket": "KOSDAQ",
              "beforeName": "가상구명", "afterName": "가상신명", "observedFrom": "2024-01-02", "observedTo": "2024-01-03"}
    context = {side: {"symbol": "000010", "isin": target["isin"], "market": "KOSDAQ", "name": target[side + "Name"], "shareType": "보통주", "knownAt": AT}
               for side in ["before", "after"]}
    return target, context


def kospi(before="구명보통주", after="신명보통주", code="000010", isin="KR0000100001"):
    return (f'<html><pre>◎ 구명 변경상장(상호변경) ① 구분(변경전 → 변경후) ㉮ 상장종목(영문명) - {before}(영문명: OLD) → {after}(영문명: NEW) '
            f'㉯ 상장종목약명 ㉰주식의 종류와 수 - 기명식 보통주 100주 ⑤ 변경상장일 : 2024년01월03일 ⑦ 코드 ▶ 보통주 표준코드:{isin} (단축코드:A{code})</pre></html>').encode()


def test_kosdaq_name_fields_allow_only_corporate_markers_and_preserve_date_role():
    t, c = target_context()
    parsed = facts.parse(body(), URL, "KOSDAQ")
    result = facts.verify(parsed, t, c)
    assert result["dateBasis"] == "EXCHANGE_NAME_CHANGE_LISTING_DATE"
    assert result["corporateLegalEffectiveDate"] is None and not result["legalMergerCompletionConfirmed"]
    assert result["sourceIsin"] is None and result["sourceStockCode"] is None
    assert facts.name_key("농업회사법인(주)구명") == "농업회사법인구명"
    assert facts.name_key("에이아이") != facts.name_key("AI")
    assert facts.name_key("구명보통주") != facts.name_key("구명")


@pytest.mark.parametrize("mutation", ["before", "after", "date", "isin", "class", "code", "market", "duplicate", "correction", "form"])
def test_mismatching_names_dates_identities_or_forms_require_review(mutation):
    t, c = target_context()
    raw = body()
    url, market = URL, "KOSDAQ"
    if mutation == "before": raw = body(before="다른회사")
    if mutation == "after": raw = body(after="다른회사")
    if mutation == "date": raw = body(stamp="2024-01-02")
    if mutation == "isin": c["before"]["isin"] = "KR9999999999"
    if mutation == "class": c["after"]["shareType"] = "우선주"
    if mutation == "code": c["after"]["symbol"] = "999999"
    if mutation == "market": market = "KOSPI"
    if mutation == "duplicate": raw = raw.replace(b'</table>', '<tr><td>4.상장일</td><td>2024-01-03</td></tr></table>'.encode())
    if mutation == "correction": raw = body(corrected=True)
    if mutation == "form": url = URL.replace('70765', '99999')
    with pytest.raises(ResearchError):
        facts.verify(facts.parse(raw, url, market), t, c)


def test_kospi_requires_source_isin_code_and_full_before_after_names():
    t, c = target_context()
    for side in ["before", "after"]:
        t[side + "Market"] = c[side]["market"] = "KOSPI"
        t[side + "Name"] = c[side]["name"] = "구명보통주" if side == "before" else "신명보통주"
    url = URL.replace('70765', '68155')
    result = facts.verify(facts.parse(kospi(), url, 'KOSPI'), t, c)
    assert result['sourceIsin'] == t['isin']
    for raw in [kospi(code="999999"), kospi(isin="KR9999999999"), kospi(after="다른회사보통주")]:
        with pytest.raises(ResearchError): facts.verify(facts.parse(raw, url, 'KOSPI'), t, c)


class NameClient(Client):
    def fetch(self, spec):
        raw = super().fetch(spec)
        if '/external/' in spec['url']:
            return body()
        return raw


def prepared_facts(tmp_path, monkeypatch):
    folder, p = planned(tmp_path)
    parent = __import__('json').loads(p.read_bytes())
    for side in ['before', 'after']:
        parent['rows'][0]['observation'][side]['market'] = 'KOSDAQ'
    obs = parent['rows'][0]['observation']
    identity = digest(canonical(obs)); parent['rows'][0]['observationId'] = identity
    p.write_bytes(canonical(parent))
    folder = tmp_path / 'name-job'; acquisition.prepare(folder, p, 10)
    monkeypatch.setattr(acquisition, 'now', lambda: AT)
    acquisition.collect(folder, NameClient(), 10, sleep=lambda _: None)
    t, c = target_context()
    c['after']['knownAt'] = LATER
    return folder, parent, {identity: c}


def test_fact_known_at_includes_later_krx_context_and_original_sources(tmp_path, monkeypatch):
    folder, parent, contexts = prepared_facts(tmp_path, monkeypatch)
    result = facts.build(folder, parent, contexts)
    assert result['verified'] == 1 and result['reviewRequired'] == 0
    f = result['facts'][0]
    assert f['knownAt'] == LATER and len(f['versions'][0]['acquisitionHashes']) == 4
    assert f['corporateLegalEffectiveDate'] is None


def test_extra_viewer_version_not_in_search_scope_remains_review(tmp_path, monkeypatch):
    folder, parent, contexts = prepared_facts(tmp_path, monkeypatch)
    raw_path = folder / 'raw/0002.bin'
    raw = raw_path.read_bytes().replace(b'</select>', '<option value="20240202000001|Y">[정정]변경상장 (2024.02.02)</option></select>'.encode())
    raw_path.write_bytes(raw)
    from app.replay.krx_storage import atomic_json
    j = __import__('json').loads((folder / 'journal.json').read_bytes()); j['attempts'][1]['sha256'] = digest(raw); atomic_json(folder / 'journal.json', j)
    result = facts.build(folder, parent, contexts)
    assert result['verified'] == 0 and result['reviews'][0]['diagnostic'] == 'NAME_FACT_VERSION_LINEAGE_REVIEW'
    assert result['reviews'][0]['knownAt'] == LATER


def test_transfer_label_needs_audited_transfer_and_exact_identity():
    t, c = target_context()
    t['beforeName'] = c['before']['name'] = '가상회사'
    t['afterName'] = c['after']['name'] = '가상회사보통주'
    t['afterMarket'] = c['after']['market'] = 'KOSPI'
    from test_universe_reconciliation import observation, issue
    obs = observation('MARKET_TRANSFER_OBSERVED', before=issue(market='KOSDAQ', name=t['beforeName']), after=issue(name=t['afterName']))
    row = {'observation': obs, 'observationId': digest(canonical(obs)), 'resolution': 'DISCLOSURE_MATCH',
           'membershipDateConfirmedByDisclosure': True, 'exchangeMembershipDate': '2024-01-03', 'evidence': [{'sourceSha256': 'b'*64}], 'knownAt': AT}
    parent = {'rows': [row]}
    result = facts.transfer_fact(t, parent, c)
    assert result['classification'] == 'MARKET_TRANSFER_COMMON_SHARE_LABEL'
    assert not result['corporateNameChangeConfirmed']
    parent['rows'][0]['resolution'] = 'STATUS_LIST_MATCH'
    with pytest.raises(ResearchError): facts.transfer_fact(t, parent, c)


class CorrectionClient(Client):
    def __init__(self, changed=False):
        super().__init__()
        self.changed = changed

    def fetch(self, spec):
        self.calls += 1
        if 'details.do' in spec['url']:
            return search(('변경상장(상호변경)', '[정정]변경상장(상호변경)'))
        if 'acptno=' in spec['url']:
            return viewer(extra='<option value="20240102000003|Y">[정정]변경상장(상호변경) (2024.01.02)</option>')
        if spec['method'] == 'POST':
            doc = spec['parameters']['docNo']
            return f"parent.setPath('','https://kind.krx.co.kr/external/2024/01/02/000001/{doc}/70765.htm','/external/x','03','13');".encode()
        corrected = '20240102000003' in spec['url']
        return body(after='다른이름' if self.changed and corrected else '가상신명 주식회사', corrected=corrected)


@pytest.mark.parametrize('changed', [False, True])
def test_correction_chain_requires_same_formal_names_and_listing_date(tmp_path, monkeypatch, changed):
    folder, p = planned(tmp_path)
    parent = __import__('json').loads(p.read_bytes())
    for side in ['before', 'after']: parent['rows'][0]['observation'][side]['market'] = 'KOSDAQ'
    identity = digest(canonical(parent['rows'][0]['observation']))
    parent['rows'][0]['observationId'] = identity; p.write_bytes(canonical(parent))
    folder = tmp_path / 'correction-job'; acquisition.prepare(folder, p, 10)
    monkeypatch.setattr(acquisition, 'now', lambda: AT)
    acquisition.collect(folder, CorrectionClient(changed), 10, sleep=lambda _: None)
    _, context = target_context()
    r = facts.build(folder, parent, {identity: context})
    if changed:
        assert r['verified'] == 0 and r['reviews'][0]['diagnostic'] == 'NAME_FACT_CORRECTION_CHANGES_NAME_FIELDS'
    else:
        assert r['verified'] == 1 and len(r['facts'][0]['versions']) == 2
        assert r['facts'][0]['otherCorrectionContentInterpreted'] is False


def test_source_common_share_suffix_bridge_needs_explicit_isin():
    assert facts.name_matches('용평리조트보통주', '주식회사 용평리조트', 'KOSPI', 'KR0000100001')
    assert not facts.name_matches('용평리조트보통주', '주식회사 용평리조트', 'KOSPI')
    assert not facts.name_matches('용평리조트보통주', '주식회사 용평리조트', 'KOSDAQ', 'KR0000100001')


def test_explicit_source_abbreviation_can_bind_krx_name_without_transliteration():
    t, c = target_context()
    raw = body(after='가상신명코퍼레이션').replace(b'</table>', '<tr><td>약명</td><td>한글</td><td>가상신명</td></tr></table>'.encode())
    f = facts.verify(facts.parse(raw, URL, 'KOSDAQ'), t, c)
    assert f['afterName'] == '가상신명코퍼레이션' and f['observedAfterName'] == '가상신명'
    assert f['nameMatchBasis']['after'] == 'DECLARED_ABBREVIATED_NAME_TO_KRX_NAME'
    with pytest.raises(ResearchError):
        facts.verify(facts.parse(body(after='가상신명코퍼레이션'), URL, 'KOSDAQ'), t, c)


def test_combined_notice_extracts_only_name_section_and_does_not_confirm_other_actions():
    raw = kospi().replace('<pre>'.encode(), '<pre>◎ 구명 변경상장(액면병합) ⑤ 변경상장일 : 2024년01월01일 '.encode())
    # Keep the distinct name section marker so unrelated action dates cannot be selected.
    f = facts.parse(raw, URL.replace('70765', '68151'), 'KOSPI')
    assert f['date'] == '2024-01-03' and f['combinedNotice']
    assert f['otherCorporateActionsConfirmed'] is False
    duplicated = raw.replace(b'</pre>', '◎ 다른 변경상장(상호변경)</pre>'.encode())
    with pytest.raises(ResearchError): facts.parse(duplicated, URL.replace('70765', '68151'), 'KOSPI')


def test_kospi_settlement_field_does_not_shift_name_date_to_wrong_role():
    raw = kospi().replace('⑤ 변경상장일'.encode(), '⑤ 결산일 : 12월 말일 ⑥ 변경상장일'.encode())
    f = facts.parse(raw, URL.replace('70765', '68155'), 'KOSPI')
    assert f['date'] == '2024-01-03'


def test_empty_unreviewed_table_has_explicit_diagnostic_instead_of_index_error():
    raw = '<html><div class="xforms_title">변경상장(상호변경)</div><table><tr></tr></table></html>'.encode()
    with pytest.raises(ResearchError, match='NAME_FACT_TABLE_AMBIGUOUS'):
        facts.parse(raw, URL, 'KOSDAQ')
