"""Fixed remaining inventory, isolated new-listing phase and bounded exact-code discovery."""
import pytest

from app.replay import listing_disclosure_coverage as coverage
from app.replay.dataset import canonical, digest, read_bytes, read_json
from app.replay.krx_storage import atomic_json
from app.replay.models import ResearchError
from test_universe_reconciliation import observation, issue, resolve, source_row
from test_kind_membership_evidence import Client, search, viewer, path


def planned(tmp_path):
    rows = []
    for kind, code, event in [('ADDED_OBSERVED', '000010', '신규상장'), ('ADDED_OBSERVED', '000020', '재상장'), ('REMOVED_OBSERVED', '000030', '자진폐지')]:
        stock = issue(code, 'KOSDAQ'); obs = observation(kind, after=stock) if kind == 'ADDED_OBSERVED' else observation(kind, before=stock)
        ref = source_row('LISTING' if kind == 'ADDED_OBSERVED' else 'DELISTING', 'KOSDAQ', key=code[:5], event_type=event)
        row, _ = resolve(obs, [ref]); assert row['resolution'] == 'STATUS_LIST_MATCH'; rows.append(row)
    parent = {'schemaVersion': 'SAGOPALGO_UNIVERSE_RECONCILIATION_V4', 'sourceKind': 'SYNTHETIC',
        'startDate': '2024-01-02', 'endDate': '2024-01-04', 'rows': rows}
    p, inv, job = tmp_path/'parent.json', tmp_path/'inventory.json', tmp_path/'job'
    p.write_bytes(canonical(parent)); coverage.prepare(job, p, inv, 8)
    return job, p, inv


def test_inventory_keeps_other_types_and_phase_only_captures_new_listings(tmp_path):
    job, p, inv = planned(tmp_path)
    report = read_json(read_bytes(inv)); plan, _, _ = coverage.load(job)
    assert report['remaining'] == 3 and report['categoryCounts'] == {'NEW_LISTING': 1, 'RELISTING': 1, 'DELISTING': 1}
    assert report['auditedFactReuseAvailable'] == 0 and len(plan['targets']) == 1
    client = Client()
    assert coverage.collect(job, client, 2, sleep=lambda _:None)['states'] == {'PENDING': 1}
    assert coverage.collect(job, client, 3, sleep=lambda _:None)['states'] == {'BODIES_CAPTURED': 1}
    assert coverage.collect(job, Client(fail=1), 8)['attemptsUsed'] == len(client.calls) == 4
    assert report == read_json(read_bytes(inv))


@pytest.mark.parametrize('variant', ['duplicate', 'status_date', 'market', 'event', 'schema'])
def test_ambiguous_parent_or_status_cannot_create_scope(tmp_path, variant):
    _, p, _ = planned(tmp_path); parent = read_json(read_bytes(p))
    if variant == 'duplicate': parent['rows'] *= 2
    if variant == 'status_date': parent['rows'][0]['evidence'][0]['date'] = '2024-01-04'
    if variant == 'market': parent['rows'][0]['evidence'][0]['market'] = 'KOSPI'
    if variant == 'event': parent['rows'][0]['evidence'][0]['eventType'] = '알수없음'
    if variant == 'schema': parent['schemaVersion'] = 'SAGOPALGO_UNIVERSE_RECONCILIATION_V3'
    with pytest.raises(ResearchError): coverage.inventory(parent, 'f'*64)


@pytest.mark.parametrize('variant', ['raw', 'request', 'orphan'])
def test_tampering_is_detected_before_a_new_http_request(tmp_path, variant):
    job, _, _ = planned(tmp_path); coverage.collect(job, Client(), 4, sleep=lambda _:None)
    if variant == 'raw': (job/'raw/0001.bin').write_bytes(b'changed')
    else:
        j = read_json(read_bytes(job/'journal.json'))
        if variant == 'request': j['attempts'][0]['request']['parameters']['repIsuSrtCd'] = 'A999999'
        else: j['attempts'][0]['stage'] = 'V3_BODY'
        atomic_json(job/'journal.json', j)
    c = Client(fail=1)
    with pytest.raises(ResearchError): coverage.collect(job, c, 1)
    assert not c.calls


def test_explicit_retry_preserves_failure_and_respects_stage_budget(tmp_path):
    job, _, _ = planned(tmp_path)
    assert coverage.collect(job, Client(fail=1), 8)['attemptsUsed'] == 1
    assert coverage.collect(job, Client(fail=1), 8)['attemptsUsed'] == 1
    assert coverage.collect(job, Client(), 8, True, sleep=lambda _:None)['states'] == {'BODIES_CAPTURED': 1}
    assert coverage.load(job)[1]['attempts'][0]['state'] == 'FAILED'


def test_correction_search_retains_both_versions_in_receipt_order():
    raw = (search().decode().split('<div')[0] + search('[정정]신규상장').decode().split('<div')[0].replace('20240102000001','20240102000003')
           + '<div class="info type-00">전체 2건 : 1 /1</div>').encode()
    assert [v['corrected'] for v in coverage.candidates(raw)] == [False, True]
    with pytest.raises(ResearchError): coverage.candidates(search(pages=2))


def test_budget_does_not_create_partial_phase(tmp_path):
    _, p, _ = planned(tmp_path)
    with pytest.raises(ValueError): coverage.prepare(tmp_path/'small', p, tmp_path/'other-inventory.json', 3)
    assert not (tmp_path/'small').exists() and not (tmp_path/'other-inventory.json').exists()
