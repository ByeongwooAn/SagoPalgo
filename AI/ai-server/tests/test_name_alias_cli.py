"""Full new CLI capture/build/audit/as-of plus immutable saved output and source preflight."""
import json

from app.replay import name_alias_evidence as acquisition, name_alias_facts as facts, name_alias_reconciliation as ledger
from app.replay.dataset import canonical
from test_name_alias_evidence import planned, Client
from test_name_alias_facts import target_context, alias_body, AT, LATER


def test_cli_audits_parent_and_preserves_v3_and_output(tmp_path, monkeypatch, capsys):
    job, p, cases = planned(tmp_path)
    parent = json.loads(p.read_bytes()); parent.update(nameDisclosureMatched=285)
    parent['rows'][1]['nameReview'] = {'diagnostic': 'OLD_REVIEW', 'knownAt': AT}
    # The final parent bytes must be fixed before planning the tested job.
    p.write_bytes(canonical(parent)); job = tmp_path / 'final-job'; acquisition.prepare(job, p, cases, 6)
    class AliasClient(Client):
        def fetch(self, spec):
            value = super().fetch(spec)
            return alias_body() if '/external/' in spec['url'] else value
    monkeypatch.setattr(acquisition.engine, 'now', lambda: LATER)
    acquisition.collect(job, AliasClient(), 3, sleep=lambda _: None)
    identity = parent['rows'][1]['observationId']; _, context = target_context()
    monkeypatch.setattr(facts, 'contexts', lambda *_: {identity: context})
    calls = []
    def audited(_): calls.append('audit'); return parent
    monkeypatch.setattr(ledger, 'audited_parent', audited)
    output, fact_path = tmp_path / 'v4.json', tmp_path / 'facts.json'
    args = []
    for flag in ['history-job','history-derived','status-job','cases','case-report','events','event-report','cache','parent-report','evidence-job','parent-v2','name-job']:
        args += ['--'+flag, str(tmp_path / flag)]
    args += ['--parent-v3',str(p),'--alias-job',str(job),'--alias-cases',str(cases),'--output',str(output),'--facts-output',str(fact_path)]
    assert ledger.main(['build',*args]) == 0; original = output.read_bytes(); capsys.readouterr()
    assert ledger.main(['audit',*args]) == 0 and output.read_bytes() == original; capsys.readouterr()
    assert ledger.main(['as-of',*args,'--at',AT]) == 0
    assert json.loads(capsys.readouterr().out)['visibleObservations'] == 1
    assert ledger.main(['as-of',*args,'--at',LATER]) == 0
    assert json.loads(capsys.readouterr().out)['visibleObservations'] == 2
    assert len(calls) == 4 and p.read_bytes() == canonical(parent)
    output.write_bytes(b'{}')
    assert ledger.main(['audit',*args]) == 2 and output.read_bytes() == b'{}'


def test_new_capture_cli_invalid_input_never_echoes_data(tmp_path, capsys):
    p = tmp_path / 'parent.json'; p.write_text('{"secret":"do-not-echo"}')
    s = tmp_path / 'cases.json'; s.write_text('{}')
    assert acquisition.main(['plan','--job',str(tmp_path/'job'),'--parent',str(p),'--cases',str(s)]) == 2
    assert 'do-not-echo' not in capsys.readouterr().out
