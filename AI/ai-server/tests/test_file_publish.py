"""Windows lock recovery, permanent failure durability and provider-call boundaries."""
import ctypes
from ctypes import wintypes
import errno
import os
from pathlib import Path
import threading

import pytest

from app.replay import file_publish as files, history, dart_history, dataset, stored
from app.replay.dataset import canonical, read_json
from tests.test_history import job as kis_job, FakeTransport as KisTransport
from tests.test_dart_history import job as dart_job, FakeTransport as DartTransport
from tests.test_replay import inputs
from tests.test_stored_conversion import fixture as stored_fixture, config as stored_config


def windows_error(code):
    error=PermissionError(errno.EACCES,'controlled publication failure');error.winerror=code
    return error


@pytest.mark.parametrize('code',[5,32,33])
def test_transient_windows_replace_retries_same_prepared_bytes_only(tmp_path,monkeypatch,code):
    source=tmp_path/'prepared';target=tmp_path/'published';source.write_bytes(b'new');target.write_bytes(b'old')
    original=os.replace;calls=[];waits=[]
    def replace(a,b):
        calls.append((a,b))
        assert source.read_bytes()==b'new'
        if len(calls)<3:
            assert target.read_bytes()==b'old'
            raise windows_error(code)
        return original(a,b)
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'replace',replace);monkeypatch.setattr(files.time,'sleep',waits.append)
    files.replace_file(source,target)
    assert len(calls)==3 and len(set(calls))==1 and waits==[0.05,0.1]
    assert target.read_bytes()==b'new' and not source.exists()


def test_persistent_access_failure_is_bounded_and_keeps_both_versions(tmp_path,monkeypatch):
    path=tmp_path/'journal.json';path.write_bytes(canonical({'attempts':[]}));calls=[];waits=[]
    def denied(*args):calls.append(args);raise windows_error(5)
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'replace',denied);monkeypatch.setattr(files.time,'sleep',waits.append)
    with pytest.raises(PermissionError):history.atomic_json(path,{'attempts':[{'state':'RESERVED'}]})
    assert read_json(path.read_bytes())=={'attempts':[]}
    assert read_json(path.with_name('journal.json.tmp').read_bytes())=={'attempts':[{'state':'RESERVED'}]}
    assert len(calls)==8 and len(waits)==7 and sum(waits)==pytest.approx(1.95)


@pytest.mark.parametrize('windows,code',[(False,5),(True,None),(True,2),(True,183)])
def test_unrelated_or_non_windows_failures_propagate_without_retry(tmp_path,monkeypatch,windows,code):
    source=tmp_path/'source';target=tmp_path/'target';source.write_bytes(b'new');calls=[]
    def fail(*args):calls.append(args);raise windows_error(code)
    monkeypatch.setattr(files,'WINDOWS',windows);monkeypatch.setattr(files.os,'replace',fail)
    monkeypatch.setattr(files.time,'sleep',lambda _:pytest.fail('must not retry'))
    with pytest.raises(PermissionError):files.replace_file(source,target)
    assert len(calls)==1 and source.read_bytes()==b'new' and not target.exists()


@pytest.mark.parametrize('collector',['kis','dart'])
def test_permanent_reservation_publish_failure_never_calls_provider(tmp_path,monkeypatch,collector):
    if collector=='kis':folder,_=kis_job(tmp_path);client=KisTransport(folder);collect=history.collect
    else:folder=dart_job(tmp_path);client=DartTransport();collect=dart_history.collect
    before=(folder/'journal.json').read_bytes()
    def denied(*args):raise windows_error(5)
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'replace',denied);monkeypatch.setattr(files.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):collect(folder,client,sleeper=lambda _:None)
    assert client.calls==[] and (folder/'journal.json').read_bytes()==before
    assert (folder/'journal.json.tmp').is_file()


@pytest.mark.parametrize('collector',['kis','dart'])
def test_checkpoint_and_jsonl_recovery_does_not_repeat_provider_calls(tmp_path,monkeypatch,collector):
    if collector=='kis':folder,_=kis_job(tmp_path);client=KisTransport(folder);collect=history.collect
    else:folder=dart_job(tmp_path);client=DartTransport();collect=dart_history.collect
    original=os.replace;failed=set()
    def temporary_lock(a,b):
        if Path(b).name in {'journal.json','daily.jsonl','disclosures.jsonl'} and Path(b).name not in failed:
            failed.add(Path(b).name);raise windows_error(32)
        return original(a,b)
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'replace',temporary_lock);monkeypatch.setattr(files.time,'sleep',lambda _:None)
    result=collect(folder,client,sleeper=lambda _:None)
    journal=read_json((folder/'journal.json').read_bytes())
    assert len(client.calls)==len(journal['attempts'])
    assert all(a.get('status',a.get('state')) in {'COMPLETE','CAPTURED'} for a in journal['attempts'])
    assert ('daily.jsonl' if collector=='kis' else 'disclosures.jsonl') in failed


@pytest.mark.parametrize('kind',['dataset','stored'])
def test_fully_prepared_bundle_survives_persistent_publication_failure(tmp_path,monkeypatch,kind):
    source=tmp_path/'source.json';config=tmp_path/'config.json';output=tmp_path/'output'
    if kind=='dataset':
        spec,rows,_=inputs();source.write_bytes(b''.join(canonical(r)+b'\n' for r in rows));config.write_bytes(canonical(spec))
        operation=lambda:dataset.build_bundle(config,source,output);pattern='.replay-build-*';marker='manifest.json'
    else:
        source.write_bytes(canonical(stored_fixture()));config.write_bytes(canonical(stored_config().model_dump(mode='json')))
        operation=lambda:stored.convert_file(source,config,output);pattern='.stored-convert-*';marker='conversion.json'
    before=source.read_bytes()
    def denied(*args):raise windows_error(5)
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'rename',denied);monkeypatch.setattr(files.time,'sleep',lambda _:None)
    with pytest.raises(PermissionError):operation()
    prepared=list(tmp_path.glob(pattern))
    assert not output.exists() and source.read_bytes()==before and len(prepared)==1
    assert (prepared[0]/marker).is_file() and (prepared[0]/'records.jsonl').is_file()


def test_competing_destination_is_preserved_during_backoff(tmp_path,monkeypatch):
    source=tmp_path/'prepared';source.mkdir();(source/'data').write_bytes(b'ours');target=tmp_path/'target';calls=[]
    def locked(*args):calls.append(args);raise windows_error(32)
    def compete(_):target.mkdir();(target/'data').write_bytes(b'theirs')
    monkeypatch.setattr(files,'WINDOWS',True);monkeypatch.setattr(files.os,'rename',locked);monkeypatch.setattr(files.time,'sleep',compete)
    with pytest.raises(FileExistsError):files.publish_directory(source,target)
    assert len(calls)==1 and (target/'data').read_bytes()==b'theirs' and (source/'data').read_bytes()==b'ours'


@pytest.mark.skipif(os.name!='nt',reason='requires native Windows sharing handles')
@pytest.mark.parametrize('kind',['file','directory'])
def test_real_windows_handle_release_allows_publication_without_data_loss(tmp_path,kind):
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE;kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    source=tmp_path/'prepared';target=tmp_path/'published'
    if kind=='file':source.write_bytes(b'new');target.write_bytes(b'old');locked=target;operation=files.replace_file
    else:source.mkdir();(source/'manifest.json').write_bytes(b'complete');locked=source;operation=files.publish_directory
    handle=kernel.CreateFileW(str(locked.resolve()),0x80000000,3,None,3,0x02000000 if kind=='directory' else 0,None)
    if handle==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    guard=threading.Lock();closed=False;timer=None
    def release():
        nonlocal closed
        with guard:
            if not closed:
                kernel.CloseHandle(handle);closed=True
    try:
        # Prove the real handle blocks the native operation before testing recovery.
        with pytest.raises(PermissionError):
            (os.replace if kind=='file' else os.rename)(source,target)
        timer=threading.Timer(0.08,release);timer.start()
        operation(source,target)
    finally:
        if timer is not None:timer.cancel();timer.join()
        release()
    assert not source.exists()
    assert target.read_bytes()==b'new' if kind=='file' else (target/'manifest.json').read_bytes()==b'complete'
