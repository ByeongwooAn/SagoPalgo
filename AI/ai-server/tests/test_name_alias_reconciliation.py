"""Only unresolved V3 rows can change; old identity, disclosure counts and knowledge times persist."""
from copy import deepcopy

import pytest

from app.replay import name_alias_reconciliation as ledger, name_alias_facts as facts, universe_reconciliation as queries
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from test_name_alias_evidence import planned
from test_name_alias_facts import target_context, alias_body, issuer_body, parent_row, AT, LATER


def inputs(tmp_path, bridge=False):
    _, parent_path, _ = planned(tmp_path, 'FORMAL_ENGLISH_BRIDGE' if bridge else 'TRADING_ALIAS_NOTICE')
    import json
    parent = json.loads(parent_path.read_bytes()); row = parent['rows'][1]
    parent.update(nameDisclosureMatched=285, nameReviewRequired=1, transferNameLabelsExplained=3)
    row['nameReview'] = parent_row()['nameReview'] if bridge else {'diagnostic': 'OLD_REVIEW', 'knownAt': AT}
    t, c = target_context()
    f = facts.bridge_fact(facts.parse_issuer(issuer_body()), t, c, row) if bridge else facts.alias_fact(facts.parse_alias(alias_body()), t, c)
    f.update(observationId=row['observationId'], stockCode=t['symbol'], historyIsin=t['isin'], market='KOSDAQ',
             knownAt=LATER, instrumentContext=c)
    s = {'parentSha256': 'f'*64, 'sourceKind': 'SYNTHETIC', 'facts': [f], 'reviews': [], 'targets': 1}
    return parent, s


@pytest.mark.parametrize('bridge', [False, True])
def test_overlay_preserves_parent_other_rows_and_legal_limits(tmp_path, bridge):
    p, s = inputs(tmp_path, bridge); frozen = canonical(p)
    r = ledger.overlay(p, s, 'f'*64); row = r['rows'][1]
    assert canonical(p) == frozen and r['rows'][0] == p['rows'][0]
    assert row['observation'] == p['rows'][1]['observation']
    assert row['previousNameReview'] == p['rows'][1]['nameReview'] and 'nameReview' not in row
    assert row['knownAt'] == LATER and row['corporateLegalNameEffectiveDate'] is None
    assert r['nameDisclosureMatched'] == 286 and r['nameReviewRequired'] == r['unresolvedObservations'] == 0
    assert r['nameTradingAliasMatched'] == (0 if bridge else 1)
    assert r['nameFormalIdentitiesBridged'] == (1 if bridge else 0)
    for key in ['membershipMatched', 'disclosureMatched', 'membershipAwaitingIndividualDisclosure', 'supplementCorrectionHeaderDateIssues']:
        assert r[key] == p[key]
    assert len(queries.as_of(r, AT)['rows']) == 1
    assert len(queries.as_of(r, LATER)['rows']) == 2
    assert not r['usableForTraining']


@pytest.mark.parametrize('field,value', [('stockCode', '999999'), ('historyIsin', 'KR9999999999'), ('market', 'KOSPI'),
    ('beforeName', '다른이름'), ('date', '2024-01-02'), ('classification', 'LEGAL_NAME_CHANGED'), ('observationId', 'a'*64)])
def test_unrelated_or_wrong_identity_fact_is_rejected(tmp_path, field, value):
    p, s = inputs(tmp_path); s['facts'][0][field] = value
    with pytest.raises(ResearchError): ledger.overlay(p, s, 'f'*64)


@pytest.mark.parametrize('variant', ['duplicate', 'missing', 'overlap', 'parent', 'source_kind', 'body_alias'])
def test_scope_and_body_evidence_cannot_be_forged(tmp_path, variant):
    p, s = inputs(tmp_path)
    if variant == 'duplicate': s['facts'] *= 2
    if variant == 'missing': s['facts'] = []
    if variant == 'overlap': s['reviews'] = [{'observationId': s['facts'][0]['observationId'], 'knownAt': LATER}]
    if variant == 'parent': s['parentSha256'] = 'a'*64
    if variant == 'source_kind': s['sourceKind'] = 'PROVIDER_OBSERVATIONS'
    if variant == 'body_alias': s['facts'][0]['beforeAlias'] = '다른약명'
    with pytest.raises(ResearchError): ledger.overlay(p, s, 'f'*64)


def test_new_review_remains_unresolved_and_is_hidden_until_known(tmp_path):
    p, s = inputs(tmp_path); identity = s['facts'][0]['observationId']; s['facts'] = []
    s['reviews'] = [{'observationId': identity, 'diagnostic': 'NEW_REVIEW', 'knownAt': LATER}]
    r = ledger.overlay(p, s, 'f'*64)
    assert r['nameReviewRequired'] == r['unresolvedObservations'] == 1
    assert r['rows'][1]['nameReview'] == p['rows'][1]['nameReview']
    assert len(queries.as_of(r, AT)['rows']) == 1
