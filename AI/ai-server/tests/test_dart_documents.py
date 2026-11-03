import io
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from app.replay.dart_documents import audit_document, capture_document, inspect_zip, main
from app.replay.dart_history import collect
from app.replay.models import ResearchError
from test_dart_history import FakeTransport, job


def archive(name="original.xml", body=b"<document>synthetic</document>"):
    stream = io.BytesIO()
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as zipfile:
        entry = ZipInfo("fixture.xml")
        entry.filename = name  # Preserve malicious separators; Windows ZipInfo normalizes constructor input.
        entry.compress_type = ZIP_DEFLATED
        zipfile.writestr(entry, body)
    return stream.getvalue()


class DocumentTransport:
    def __init__(self, body=None, fail=False): self.body = archive() if body is None else body; self.calls = []; self.fail = fail
    def fetch(self, endpoint, params):
        self.calls.append((endpoint, params))
        if self.fail: raise ResearchError("DART_HTTP_FAILED")
        return self.body


def index(tmp_path):
    target = job(tmp_path)
    collect(target, FakeTransport(), sleeper=lambda _: None)
    return target


def test_selected_original_is_bound_to_audited_index_and_reused_without_changing_index(tmp_path):
    source = index(tmp_path)
    originals = {name: (source / name).read_bytes() for name in ["report.json", "disclosures.jsonl", "journal.json"]}
    client = DocumentTransport()
    output = tmp_path / "original"
    value, cached = capture_document(source, "20240102000000", output, client)
    assert not cached and value["status"] == "ORIGINAL_CAPTURED" and len(value["entries"]) == 1
    assert value["referenceEventsEmitted"] == 0 and not value["effectiveEventConfirmed"]
    assert value["indexInstrumentScope"] == "UNVERIFIED" and value["maxRequests"] == 1
    assert client.calls == [("document", {"rcept_no": "20240102000000"})]
    assert audit_document(output) == value
    assert capture_document(source, "20240102000000", output, client) == (value, True)
    assert len(client.calls) == 1 and not (output / "original.xml").exists()
    assert all((source / name).read_bytes() == raw for name, raw in originals.items())


@pytest.mark.parametrize("receipt", ["invalid", "20240102999999"])
def test_unindexed_receipt_is_rejected_before_network_or_output(tmp_path, receipt):
    source = index(tmp_path)
    client = DocumentTransport()
    with pytest.raises(ResearchError, match="RECEIPT_INVALID|NOT_IN_INDEX"):
        capture_document(source, receipt, tmp_path / "original", client)
    assert not client.calls and not (tmp_path / "original").exists()


@pytest.mark.parametrize("name", ["../original.xml", "/original.xml", "C:/original.xml", "bad\\original.xml"])
def test_untrusted_zip_paths_are_rejected_without_extraction(name):
    with pytest.raises(ResearchError, match="ENTRY_INVALID"):
        inspect_zip(archive(name))


def test_archive_count_size_and_crc_or_format_are_checked():
    stream = io.BytesIO()
    with ZipFile(stream, "w") as zipped:
        for number in range(33): zipped.writestr(f"{number}.xml", b"x")
    with pytest.raises(ResearchError, match="ARCHIVE_LIMIT"): inspect_zip(stream.getvalue())
    with pytest.raises(ResearchError, match="ENTRY_INVALID"): inspect_zip(archive(body=b"x" * (8 * 1024 * 1024 + 1)))
    with pytest.raises(ResearchError, match="ZIP_INVALID"): inspect_zip(b'<result><status>013</status></result>')


@pytest.mark.parametrize("fail", [False, True])
def test_failed_original_capture_is_reserved_and_never_auto_retried(tmp_path, fail):
    source = index(tmp_path)
    client = DocumentTransport(b"not-zip", fail)
    output = tmp_path / "original"
    with pytest.raises(ResearchError): capture_document(source, "20240102000000", output, client)
    assert json.loads((output / "capture.json").read_bytes())["status"] == "FAILED"
    with pytest.raises(ResearchError, match="INCOMPLETE"): capture_document(source, "20240102000000", output, client)
    assert len(client.calls) == 1


def test_tampered_document_and_other_receipt_cannot_reuse_capture(tmp_path):
    source = index(tmp_path)
    output = tmp_path / "original"
    client = DocumentTransport()
    capture_document(source, "20240102000000", output, client)
    with pytest.raises(ResearchError, match="BINDING_MISMATCH"):
        capture_document(source, "20240102000001", output, client)
    (output / "original.zip").write_bytes(b"changed")
    with pytest.raises(ResearchError, match="TAMPERED"): audit_document(output)
    assert len(client.calls) == 1


def test_original_audit_cli_uses_no_credentials_or_network(tmp_path, monkeypatch, capsys):
    source = index(tmp_path)
    output = tmp_path / "original"
    capture_document(source, "20240102000000", output, DocumentTransport())
    monkeypatch.delenv("SAGOPALGO_OPEN_DART_API_KEY", raising=False)
    assert main(["audit", "--capture", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["entryCount"] == 1
