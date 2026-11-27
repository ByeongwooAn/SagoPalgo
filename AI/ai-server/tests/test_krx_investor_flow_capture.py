from datetime import date, timedelta
import json

import pytest

from app.replay import krx_investor_flow_capture as flow

TRADING_DAY = date(2026, 11, 27)


def body(target=TRADING_DAY, volume=100):
    row = {"stck_bsop_date": target.strftime("%Y%m%d"), "acml_vol": str(volume), "acml_tr_pbmn": "10000"}
    for group in ("prsn", "orgn", "frgn"):
        row.update({f"{group}_shnu_vol": "10", f"{group}_seln_vol": "12", f"{group}_ntby_qty": "-2",
                    f"{group}_shnu_tr_pbmn": "3", f"{group}_seln_tr_pbmn": "4", f"{group}_ntby_tr_pbmn": "0"})
    return json.dumps({"rt_cd": "0", "output2": [row]}).encode()


class Clock:
    def __init__(self, current):
        self.current = current

    def __call__(self):
        return self.current

    def sleep(self, seconds):
        self.current += timedelta(seconds=seconds)


class Transport:
    def __init__(self, clock, raw, delays=None):
        self.clock, self.raw, self.delays = clock, raw, delays or {}
        self.requests = []

    def authenticate(self):
        pass

    def fetch_flow(self, code, target):
        self.requests.append((code, target))
        self.clock.sleep(self.delays.get(code, 1))
        return 200, self.raw, self.clock()


def test_close_uses_receipt_time_and_excludes_late_second_symbol(tmp_path, monkeypatch):
    clock = Clock(flow.window("close", TRADING_DAY)[0])
    transport = Transport(clock, body(), {"005930": 1, "000660": 30})
    (tmp_path / "receipt.json").write_text("{}")
    monkeypatch.setattr(flow, "open_day", lambda *args: (True, tmp_path))

    result = flow.run("close", tmp_path, tmp_path, lambda: transport, clock, clock.sleep)

    assert transport.requests == [("005930", TRADING_DAY), ("000660", TRADING_DAY)]
    assert result["status"] == "CAPTURE_INCOMPLETE"
    assert result["tickers"]["005930"]["close"]
    assert result["tickers"]["000660"]["close"] is None
    assert not result["commonByCutoff"]
    assert len(list((tmp_path / TRADING_DAY.isoformat()).glob("*/body.json"))) == 2


def test_next_calendar_day_keeps_close_evidence_and_reports_change(tmp_path, monkeypatch):
    clock = Clock(flow.window("close", TRADING_DAY)[1])
    initial = Transport(clock, body())
    (tmp_path / "receipt.json").write_text("{}")
    monkeypatch.setattr(flow, "open_day", lambda *args: (True, tmp_path))
    before = flow.run("close", tmp_path, tmp_path, lambda: initial, clock, clock.sleep)
    duplicate = flow.run("close", tmp_path, tmp_path, lambda: pytest.fail("duplicate network call"), clock)
    assert before == duplicate

    clock.current = flow.window("next-day", TRADING_DAY)[1]
    assert clock.current.weekday() == 5
    later = Transport(clock, body(volume=105))
    after = flow.run("next-day", tmp_path, tmp_path, lambda: later, clock)
    assert after["commonByCutoff"]
    assert later.requests == [("005930", TRADING_DAY), ("000660", TRADING_DAY)]
    for code in flow.TICKERS:
        assert after["tickers"][code]["close"] == before["tickers"][code]["close"]
        assert after["tickers"][code]["changedFields"] == ["acml_vol"]


def test_closed_day_and_missing_previous_evidence_skip_quote_requests(tmp_path, monkeypatch):
    clock = Clock(flow.window("close", TRADING_DAY)[0])
    transport = Transport(clock, body())
    (tmp_path / "receipt.json").write_text("{}")
    monkeypatch.setattr(flow, "open_day", lambda *args: (False, tmp_path))
    assert flow.run("close", tmp_path, tmp_path, lambda: transport, clock)["status"] == "CLOSED"
    assert not transport.requests
    clock.current = flow.window("next-day", TRADING_DAY)[0]
    assert flow.run("next-day", tmp_path, tmp_path, lambda: pytest.fail("unexpected network call"), clock)[
        "status"] == "NO_PRIOR_EVIDENCE"


def test_audit_verifies_response_hash_and_cutoff_boundary(tmp_path):
    clock = Clock(flow.window("close", TRADING_DAY)[1])
    transport = Transport(clock, body(), {"005930": 30})
    flow.capture(tmp_path, "close", TRADING_DAY, "005930", transport, clock)
    assert flow.available(tmp_path, "close", TRADING_DAY, "005930")[0] == flow.window("close", TRADING_DAY)[2]
    raw = next(tmp_path.glob("*/body.json"))
    raw.write_bytes(body(volume=99))
    with pytest.raises(flow.ResearchError, match="FLOW_RESPONSE_HASH_MISMATCH"):
        flow.audit(tmp_path, TRADING_DAY)


def test_flow_rejects_invalid_fields_and_wrong_trade_date():
    assert flow.parse_flow(body(), 200, TRADING_DAY)["frgn_ntby_qty"] == -2
    assert flow.parse_flow(body(), 503, TRADING_DAY) is None
    assert flow.parse_flow(body(TRADING_DAY - timedelta(days=1)), 200, TRADING_DAY) is None
    invalid = body().replace(b'"prsn_ntby_qty": "-2"', b'"prsn_ntby_qty": "0"')
    assert flow.parse_flow(invalid, 200, TRADING_DAY) is None
