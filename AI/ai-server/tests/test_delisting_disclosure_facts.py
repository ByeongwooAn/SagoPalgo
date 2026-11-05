"""Final removal dates differ from superseded plans, liquidation dates and legal merger dates."""
from copy import deepcopy
import pytest

from app.replay import delisting_disclosure_facts as facts, delisting_revision_facts as revisions
from app.replay import delisting_revision_capture as archive, delisting_disclosure_coverage as primary
from app.replay.models import ResearchError
from test_membership_evidence_facts import body, target, AT
from test_delisting_revision_capture import PrimaryClient, ArchiveClient
from test_delisting_disclosure_coverage import planned


def source(form='70769', stamp='2024-01-03', start='-', end='-', correction=False, code='000010', suffix=''):
    raw = body(form, stamp, correction=correction, code=code, isin='KR'+code+'0001')
    reason = '5.상장폐지사유' if form == '70769' else '3.상장폐지사유'
    label = '6.정리매매기간' if form == '70769' else '5.정리매매허용기간'
    extra = (f'<tr><td>{reason}</td><td>피흡수합병</td></tr><tr><td>{label}</td><td>시작일</td><td>{start}</td>{suffix}</tr>'
             f'<tr><td>종료일</td><td>{end}</td></tr>').encode()
    # Insert into the main table, not a correction-header table.
    i = raw.rfind(b'</table>')
    return raw[:i] + extra + raw[i:]


def parse(raw, form='70769', corrected=False):
    t = {**target(form), 'statusEventType': '피흡수합병'}
    return facts.parse_fact(raw, 'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/'+form+'.htm',
                            t, AT, '가상회사', {}, corrected)


@pytest.mark.parametrize('form', ['70769', '68051'])
def test_delisting_and_declared_liquidation_dates_have_distinct_roles(form):
    f = parse(source(form, start='2024-01-01', end='2024-01-02', suffix='<td>7매매일</td>'), form)
    assert f['date'] == '2024-01-03' and f['liquidationTradingPeriod']['end'] == '2024-01-02'
    assert f['liquidationTradingPeriod']['declaredTradingSessions'] == '7매매일'
    assert not f['liquidationTradingPeriod']['actualTradingConfirmed'] and not f['delistingDateIsLiquidationEnd']
    assert f['mergerReasonStated'] and not f['legalMergerCompletionConfirmed'] and f['exchangeRatio'] is None


def test_dashes_mean_dates_not_provided_rather_than_proof_of_no_trading():
    f = parse(source())
    assert f['liquidationTradingPeriod']['status'] == 'DATES_NOT_PROVIDED'
    assert not f['liquidationTradingPeriod']['actualTradingConfirmed']


@pytest.mark.parametrize('start,end', [('2024-01-01','-'), ('2024-01-03','2024-01-02'), ('2024-01-01','2024-01-03')])
def test_partial_reversed_or_overlapping_periods_are_rejected(start, end):
    with pytest.raises(ResearchError): parse(source(start=start, end=end))


@pytest.mark.parametrize('stamp', ['2023-10-01', '-'])
def test_superseded_date_outside_observation_window_or_unset_is_only_an_announcement(stamp):
    raw = source(stamp=stamp); t = target('70769')
    a = revisions.announcement(raw, 'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/70769.htm', t, AT, {}, False)
    assert a['announcedDelistingDate'] == (None if stamp == '-' else stamp)
    assert not a['announcedDateOccurredConfirmed'] and not a['legalMergerCompletionConfirmed']
    with pytest.raises((ResearchError, ValueError)): parse(raw)


@pytest.mark.parametrize('variant', ['code','isin','market','title','rule','correction'])
def test_historical_announcement_still_requires_identity_market_and_declared_correction(variant):
    raw = source(); t = target('70769')
    if variant == 'code': raw = source(code='999999')
    if variant == 'isin': t['isin'] = 'KR9999999999'
    if variant == 'market': t['market'] = 'KOSPI'
    if variant == 'title': raw = raw.replace('>상장폐지<'.encode(), '>다른서류<'.encode())
    if variant == 'rule': raw = raw.replace('코스닥시장상장규정'.encode(), '다른규정'.encode())
    if variant == 'correction': raw = source(correction=True)
    with pytest.raises(ResearchError): revisions.announcement(raw, 'https://kind.krx.co.kr/external/2024/01/01/000001/20240101000002/70769.htm', t, AT, {}, False)


class Current(PrimaryClient):
    def fetch(self, spec):
        raw = super().fetch(spec)
        return source(code='000030', correction=True) if raw == b'<html>current source body</html>' else raw


class Previous(ArchiveClient):
    def fetch(self, spec):
        raw = super().fetch(spec)
        return source(code='000030', stamp='2023-12-01') if raw == b'<html>older source body</html>' else raw


def test_complete_chain_uses_active_current_date_and_preserves_old_plan(tmp_path):
    job, _, _ = planned(tmp_path); primary.collect(job, Current(), 8, sleep=lambda _: None)
    revision = tmp_path/'revisions'; archive.prepare(revision, job, 4)
    archive.collect(revision, job, Previous(), 4, sleep=lambda _: None)
    t = primary.load(job)[0]['targets'][0]; contexts = {t['observationId']: {'knownAt': AT}}
    base = facts.build(job, contexts)
    assert base['reviewRequired'] == 1  # The original was not in the bounded search result.
    result = revisions.build(revision, job, contexts, base)
    assert result['verified'] == 1 and result['reviewRequired'] == 0 and result['revisionVerified'] == 1, result['reviews']
    f = result['facts'][0]
    assert f['date'] == '2024-01-03' and f['announcedDateChangedByCorrection']
    assert f['versions'][0]['announcement']['announcedDelistingDate'] == '2023-12-01'
    assert f['versions'][0]['dateRole'] == 'SUPERSEDED_ANNOUNCEMENT'
    assert not f['supersededDatesOccurredConfirmed']


def test_missing_archived_body_cannot_upgrade_a_correction(tmp_path):
    job, _, _ = planned(tmp_path); primary.collect(job, Current(), 8, sleep=lambda _: None)
    revision = tmp_path/'revisions'; archive.prepare(revision, job, 4)
    t = primary.load(job)[0]['targets'][0]; contexts = {t['observationId']: {'knownAt': AT}}
    result = revisions.build(revision, job, contexts, facts.build(job, contexts))
    assert result['verified'] == 0 and result['reviewRequired'] == 1
    assert result['reviews'][0]['diagnostic'] == 'DELISTING_REVISION_PENDING'


class WrongCurrent(Current):
    def fetch(self, spec):
        raw = super().fetch(spec)
        return raw.replace(b'2024-01-03', b'2023-12-01') if spec['url'].endswith('/70769.htm') else raw


def test_complete_chain_still_rejects_current_date_outside_actual_removal_window(tmp_path):
    job, _, _ = planned(tmp_path); primary.collect(job, WrongCurrent(), 8, sleep=lambda _: None)
    revision = tmp_path/'revisions'; archive.prepare(revision, job, 4)
    archive.collect(revision, job, Previous(), 4, sleep=lambda _: None)
    t = primary.load(job)[0]['targets'][0]; contexts = {t['observationId']: {'knownAt': AT}}
    result = revisions.build(revision, job, contexts, facts.build(job, contexts))
    assert result['verified'] == 0 and result['reviews'][0]['diagnostic'] == 'MEMBERSHIP_FACT_DATE_CONFLICT'
