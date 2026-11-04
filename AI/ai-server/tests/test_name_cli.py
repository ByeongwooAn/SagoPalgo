"""CLI build/audit/as-of must audit the parent and refuse changed saved output."""
import json

from app.replay import name_disclosures as capture, name_reconciliation as ledger
from app.replay.dataset import canonical, digest
from test_name_reconciliation import inputs
from test_name_facts import NameClient, AT, LATER, target_context


def test_cli_build_audit_as_of_and_saved_output_tamper(tmp_path, monkeypatch, capsys):
    parent, _ = inputs()
    parent.update(schemaVersion='SAGOPALGO_UNIVERSE_RECONCILIATION_V2', startDate='2024-01-02', endDate='2024-01-04')
    row = parent['rows'][1]
    for side in ['before', 'after']: row['observation'][side]['market'] = 'KOSDAQ'
    identity = digest(canonical(row['observation'])); row['observationId'] = identity
    p = tmp_path / 'parent.json'; p.write_bytes(canonical(parent))
    job = tmp_path / 'job'; capture.prepare(job, p, 10)
    monkeypatch.setattr(capture, 'now', lambda: LATER)
    capture.collect(job, NameClient(), 10, sleep=lambda _: None)
    _, context = target_context()
    monkeypatch.setattr(ledger, 'contexts', lambda *_: {identity: context})
    monkeypatch.setattr(ledger.kind_cases, 'load_scope', lambda _: {})
    monkeypatch.setattr(ledger.kind_cases, 'audit_report', lambda *_: {})
    monkeypatch.setattr(ledger.universe_events, 'load_scope', lambda _: {})
    monkeypatch.setattr(ledger.universe_events, 'audit_report', lambda *_: {})
    calls = []
    def audited_parent(*_):
        calls.append('audited')
        return parent, {}
    monkeypatch.setattr(ledger.prior, 'build', audited_parent)
    output, facts = tmp_path / 'v3.json', tmp_path / 'facts.json'
    args = []
    for flag in ['history-job', 'history-derived', 'status-job', 'cases', 'case-report', 'events', 'event-report', 'cache', 'parent-report', 'evidence-job']:
        args += ['--' + flag, str(tmp_path / flag)]
    args += ['--parent-v2', str(p), '--name-job', str(job), '--output', str(output), '--facts-output', str(facts)]
    assert ledger.main(['build', *args]) == 0
    built = output.read_bytes(); capsys.readouterr()
    assert ledger.main(['audit', *args]) == 0 and output.read_bytes() == built
    capsys.readouterr()
    assert ledger.main(['as-of', *args, '--at', AT]) == 0
    assert json.loads(capsys.readouterr().out)['visibleObservations'] == 1
    assert ledger.main(['as-of', *args, '--at', LATER]) == 0
    assert json.loads(capsys.readouterr().out)['visibleObservations'] == 2
    assert len(calls) == 4 and p.read_bytes() == canonical(parent)
    output.write_bytes(b'{}')
    assert ledger.main(['audit', *args]) == 2
    assert output.read_bytes() == b'{}'


def test_capture_cli_does_not_echo_invalid_sensitive_input(tmp_path, capsys):
    p = tmp_path / 'parent.json'; p.write_text('{"private":"do-not-echo"}')
    assert capture.main(['plan', '--job', str(tmp_path / 'job'), '--parent', str(p)]) == 2
    assert 'do-not-echo' not in capsys.readouterr().out
