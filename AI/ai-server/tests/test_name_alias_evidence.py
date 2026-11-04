"""Fixed unresolved scope, approved receipt chains, shared bounded capture and source separation."""
import pytest

from app.replay import name_alias_evidence as alias
from app.replay.dataset import canonical, digest, read_bytes, read_json
from app.replay.krx_storage import atomic_json
from app.replay.models import ResearchError
from test_name_reconciliation import inputs

RECEIPT = '20240102000001'
DOC = '20240102000002'
URL = 'https://kind.krx.co.kr/external/2024/01/02/000001/' + DOC + '/70792.htm'


def planned(tmp_path, mode='TRADING_ALIAS_NOTICE'):
    parent, _ = inputs()
    parent.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V3', startDate='2024-01-02', endDate='2024-01-04')
    row = parent['rows'][1]
    for side in ['before', 'after']: row['observation'][side]['market'] = 'KOSDAQ'
    row['observationId'] = digest(canonical(row['observation']))
    scope = {'schemaVersion': 'SAGOPALGO_NAME_ALIAS_CASES_V1', 'cases': [
        {'observationId': row['observationId'], 'stockCode': '000010', 'mode': mode, 'receipt': RECEIPT}]}
    p, s, job = tmp_path / 'parent.json', tmp_path / 'cases.json', tmp_path / 'job'
    p.write_bytes(canonical(parent)); s.write_bytes(canonical(scope))
    alias.prepare(job, p, s, 6)
    return job, p, s


class Client:
    source_kind = 'SYNTHETIC'
    def __init__(self, fail=False, code='000010', extra=False, url=URL):
        self.calls = 0; self.fail = fail; self.code = code; self.extra = extra; self.url = url

    def fetch(self, spec):
        self.calls += 1
        if self.fail: raise OSError('do-not-echo')
        if 'acptno=' in spec['url']:
            extra = '<option value="20240202000001|Y">[정정]기타시장안내(약명 및 영문명) (2024.02.02)</option>' if self.extra else ''
            return (f'<h1>가상회사 ({self.code})</h1><select id="mainDoc"><option value="{DOC}|Y">기타시장안내(약명 및 영문명) (2024.01.02)</option>{extra}</select>').encode()
        if spec['method'] == 'POST': return f"parent.setPath('','{self.url}','/external/x','03','13');".encode()
        return b'<html>reviewed separately</html>'


def test_shared_engine_resumes_alias_chain_without_changing_old_default_policy(tmp_path):
    job, _, _ = planned(tmp_path); client = Client()
    assert alias.collect(job, client, 1, sleep=lambda _: None)['states'] == {'PENDING': 1}
    assert alias.collect(job, client, 2, sleep=lambda _: None)['states'] == {'BODIES_CAPTURED': 1}
    assert alias.collect(job, Client(True), 6)['attemptsUsed'] == client.calls == 3
    assert not alias.summary(job)['nameChangeConfirmed']


@pytest.mark.parametrize('variant', ['code', 'version', 'form', 'host'])
def test_wrong_viewer_unreviewed_revision_or_untrusted_path_never_reaches_body(tmp_path, variant):
    job, _, _ = planned(tmp_path)
    c = Client(code='999999') if variant == 'code' else Client(extra=True) if variant == 'version' else Client(url=URL.replace('70792', '70765')) if variant == 'form' else Client(url=URL.replace('kind.krx.co.kr', 'example.com'))
    result = alias.collect(job, c, 6, sleep=lambda _: None)
    assert result['states'] != {'BODIES_CAPTURED': 1}
    assert c.calls <= 2


def test_failed_receipt_requires_explicit_retry_and_keeps_original_attempt(tmp_path):
    job, _, _ = planned(tmp_path)
    assert alias.collect(job, Client(True), 6)['attemptsUsed'] == 1
    assert alias.collect(job, Client(True), 6)['attemptsUsed'] == 1
    assert alias.collect(job, Client(), 6, True, sleep=lambda _: None)['states'] == {'BODIES_CAPTURED': 1}
    assert alias.load(job)[1]['attempts'][0]['diagnostic'] == 'NAME_DISCLOSURES_CAPTURE_FAILED'


@pytest.mark.parametrize('variant', ['scope', 'code', 'receipt', 'budget', 'schema'])
def test_scope_is_exact_and_reviewed_modes_are_bounded(tmp_path, variant):
    job, p, s = planned(tmp_path)
    scope = read_json(read_bytes(s)); parent = read_json(read_bytes(p)); budget = 6
    if variant == 'scope': scope['cases'] *= 2
    if variant == 'code': scope['cases'][0]['stockCode'] = '999999'
    if variant == 'receipt': scope['cases'][0]['receipt'] = '20250102000001'
    if variant == 'budget': budget = 2
    if variant == 'schema': parent['schemaVersion'] = 'SAGOPALGO_UNIVERSE_RECONCILIATION_V2'
    atomic_json(s, scope); atomic_json(p, parent)
    with pytest.raises((ResearchError, ValueError)):
        alias.prepare(tmp_path / 'other', p, s, budget)


@pytest.mark.parametrize('variant', ['raw', 'request', 'orphan'])
def test_complete_cache_is_audited_before_any_new_request(tmp_path, variant):
    job, _, _ = planned(tmp_path); alias.collect(job, Client(), 3, sleep=lambda _: None)
    if variant == 'raw': (job / 'raw/0001.bin').write_bytes(b'changed')
    else:
        j = read_json(read_bytes(job / 'journal.json'))
        if variant == 'request': j['attempts'][0]['request']['url'] += '&wrong=1'
        else: j['attempts'][0]['stage'] = 'V3_BODY'
        atomic_json(job / 'journal.json', j)
    c = Client(True)
    with pytest.raises(ResearchError): alias.collect(job, c, 1)
    assert c.calls == 0
