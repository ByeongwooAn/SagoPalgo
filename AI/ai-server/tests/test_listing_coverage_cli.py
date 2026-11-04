"""CLI upgrades the selected phase only, audits the parent and refuses changed saved results."""
import json

from app.replay import listing_disclosure_coverage as capture, listing_coverage_reconciliation as ledger
from app.replay.dataset import canonical
from test_listing_disclosure_coverage import planned
from test_listing_disclosure_facts import FactClient,context,LATER


def test_cli_build_audit_as_of_and_output_tamper(tmp_path,monkeypatch,capsys):
    _,p,inv=planned(tmp_path); parent=json.loads(p.read_bytes())
    parent.update(disclosureMatched=63,membershipAwaitingIndividualDisclosure=3)
    p.write_bytes(canonical(parent)); job=tmp_path/'final-job'; inv=tmp_path/'final-inventory.json'; capture.prepare(job,p,inv,8)
    monkeypatch.setattr(capture.engine,'now',lambda:LATER)
    capture.collect(job,FactClient(),4,sleep=lambda _:None)
    identity=parent['rows'][0]['observationId']
    monkeypatch.setattr(ledger.membership,'contexts',lambda *_:{identity:context()})
    audits=[]
    def audited(_): audits.append(True); return parent
    monkeypatch.setattr(ledger,'audited_parent',audited)
    output,facts=tmp_path/'v5.json',tmp_path/'facts.json'
    args=[]
    for flag in ['history-job','history-derived','status-job','cases','case-report','events','event-report','cache',
                 'parent-report','evidence-job','parent-v2','name-job','parent-v3','alias-job','alias-cases']:
        args+=['--'+flag,str(tmp_path/flag)]
    args+=['--parent-v4',str(p),'--coverage-job',str(job),'--inventory',str(inv),'--output',str(output),'--facts-output',str(facts)]
    assert ledger.main(['build',*args])==0; before=output.read_bytes(); capsys.readouterr()
    assert ledger.main(['audit',*args])==0 and output.read_bytes()==before; capsys.readouterr()
    assert ledger.main(['as-of',*args,'--at','2026-11-04T23:59:59Z'])==0
    assert json.loads(capsys.readouterr().out)['visibleObservations']==2
    assert ledger.main(['as-of',*args,'--at',LATER])==0
    assert json.loads(capsys.readouterr().out)['visibleObservations']==3 and len(audits)==4
    assert p.read_bytes()==canonical(parent)
    output.write_bytes(b'{}')
    assert ledger.main(['audit',*args])==2 and output.read_bytes()==b'{}'


def test_capture_cli_invalid_input_does_not_echo_content(tmp_path,capsys):
    p=tmp_path/'bad.json'; p.write_text('{"private":"never-echo"}')
    assert capture.main(['plan','--job',str(tmp_path/'job'),'--parent',str(p),'--inventory',str(tmp_path/'inventory.json')])==2
    assert 'never-echo' not in capsys.readouterr().out
