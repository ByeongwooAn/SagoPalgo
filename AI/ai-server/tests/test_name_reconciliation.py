"""Name evidence cannot mutate membership results, observations, identity or past availability."""
from copy import deepcopy

import pytest

from app.replay import name_reconciliation as names, universe_reconciliation as prior
from app.replay.dataset import canonical, digest
from app.replay.models import ResearchError
from test_universe_reconciliation import observation, issue, resolve, source_row

AT = '2026-11-04T13:00:00Z'


def inputs():
    o = observation('NAME_CHANGE_OBSERVED', before=issue(name='가상구명'), after=issue(name='가상신명'))
    name_row, _ = resolve(o, [])
    member_row, _ = resolve(observation(), [source_row()])
    parent = {'sourceKind': 'SYNTHETIC', 'rows': [member_row, name_row], 'membershipMatched': 1, 'disclosureMatched': 0,
              'membershipAwaitingIndividualDisclosure': 1, 'supplementCorrectionHeaderDateIssues': 1,
              'marketUniverseComplete': False, 'usableForTraining': False, 'usableForTrading': False}
    fact = {'observationId': digest(canonical(o)), 'classification': 'EXCHANGE_NAME_CHANGE', 'stockCode': '000010',
            'historyIsin': o['isin'], 'sourceIsin': o['isin'], 'beforeName': '(주)가상구명', 'afterName': '가상신명 주식회사',
            'date': '2024-01-03', 'dateBasis': 'EXCHANGE_NAME_CHANGE_LISTING_DATE', 'knownAt': AT}
    supplement = {'parentSha256': 'f'*64, 'sourceKind': 'SYNTHETIC', 'targets': 1, 'facts': [fact], 'reviews': []}
    return parent, supplement


def test_overlay_preserves_all_membership_metadata_and_original_observations():
    parent, s = inputs(); frozen = canonical(parent)
    result = names.overlay(parent, s, 'f'*64)
    assert canonical(parent) == frozen and result['rows'][0] == parent['rows'][0]
    for key in ['membershipMatched', 'disclosureMatched', 'membershipAwaitingIndividualDisclosure', 'supplementCorrectionHeaderDateIssues']:
        assert result[key] == parent[key]
    assert result['nameDisclosureMatched'] == 1 and result['unresolvedObservations'] == 0
    row = result['rows'][1]
    assert row['observation'] == parent['rows'][1]['observation']
    assert row['observation']['effectiveDate'] is None and row['corporateLegalNameEffectiveDate'] is None
    assert not row['membershipDateConfirmedByDisclosure'] and row['exchangeMembershipDate'] is None
    assert row['knownAt'] == AT and not result['usableForTraining']
    assert not prior.as_of(result, '2026-11-04T12:30:00Z')['rows'][0].get('nameEvidenceId')
    assert len(prior.as_of(result, AT)['rows']) == 2


@pytest.mark.parametrize('field,value', [('stockCode', '999999'), ('historyIsin', 'KR9999999999'), ('beforeName', '다른회사'),
    ('afterName', '다른회사'), ('date', '2024-01-02'), ('classification', 'LEGAL_MERGER_COMPLETED'), ('observationId', 'b'*64)])
def test_overlay_rejects_unrelated_facts(field, value):
    p, s = inputs(); s['facts'][0][field] = value
    with pytest.raises(ResearchError): names.overlay(p, s, 'f'*64)


@pytest.mark.parametrize('mutation', ['duplicate', 'overlap', 'missing', 'parent', 'kind'])
def test_exact_scope_parent_and_unique_resolution_required(mutation):
    p, s = inputs()
    if mutation == 'duplicate': s['facts'] *= 2
    if mutation == 'overlap': s['reviews'] = [{'observationId': s['facts'][0]['observationId'], 'knownAt': AT}]
    if mutation == 'missing': s['facts'] = []
    if mutation == 'parent': s['parentSha256'] = 'a'*64
    if mutation == 'kind': s['sourceKind'] = 'PROVIDER_OBSERVATIONS'
    with pytest.raises(ResearchError): names.overlay(p, s, 'f'*64)


def test_unresolved_review_is_preserved_and_hidden_before_review_known_at():
    p, s = inputs(); identity = s['facts'][0]['observationId']; s['facts'] = []
    s['reviews'] = [{'observationId': identity, 'diagnostic': 'NAME_FACT_DATE_CONFLICT', 'knownAt': AT}]
    r = names.overlay(p, s, 'f'*64)
    assert r['nameReviewRequired'] == r['unresolvedObservations'] == 1
    assert r['rows'][1]['resolution'] == 'NAME_CHANGE_NEEDS_DISCLOSURE'
    assert len(prior.as_of(r, '2026-11-04T12:30:00Z')['rows']) == 1


def test_transfer_label_is_separate_from_company_name_change_count():
    p, s = inputs()
    row = p['rows'][1]; o = row['observation']
    o['before']['market'] = 'KOSDAQ'; o['after']['name'] = '가상구명보통주'
    row['observationId'] = digest(canonical(o))
    transfer = deepcopy(row); transfer['observation']['kind'] = 'MARKET_TRANSFER_OBSERVED'
    transfer['observationId'] = digest(canonical(transfer['observation']))
    transfer.update(resolution='DISCLOSURE_MATCH', membershipDateConfirmedByDisclosure=True, exchangeMembershipDate='2024-01-03')
    p['rows'].append(transfer)
    s['facts'][0].update(observationId=row['observationId'], classification='MARKET_TRANSFER_COMMON_SHARE_LABEL',
                         transferObservationId=transfer['observationId'], beforeName='가상구명', afterName='가상구명보통주')
    r = names.overlay(p, s, 'f'*64)
    assert r['transferNameLabelsExplained'] == 1 and r['nameDisclosureMatched'] == 0
    p['rows'][-1]['resolution'] = 'STATUS_LIST_MATCH'
    with pytest.raises(ResearchError): names.overlay(p, s, 'f'*64)
