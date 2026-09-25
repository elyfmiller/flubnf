"""Runs started in the same second list in the order they started.

A run id carries only its start second (plus a random suffix), so sorting
by id breaks a same-second tie at random and "the latest run" could be the
older one. The ledger's created_utc (sub-second) and its insertion order
(rowid) decide instead; the id format and its parsing are unchanged."""
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import runs as R                                  # noqa: E402
from app.ui import shared                                       # noqa: E402


def _open_same_second(monkeypatch, ledger, hexes, created=None):
    """Open one run per suffix in `hexes`, all stamped the same second
    (and, with `created`, the same created_utc); returns their ids."""
    it = iter(hexes)
    monkeypatch.setattr(R.uuid, "uuid4",
                        lambda: types.SimpleNamespace(hex=next(it) + "00"))
    monkeypatch.setattr(R.time, "strftime", lambda fmt, *a: "20980103T120000")
    if created is not None:
        monkeypatch.setattr(R.time, "time", lambda: created)
    spec = R.RunSpec(engine="analogue", forecast_date="2098-01-03",
                     locations=["Ohio"])
    ids = [ledger.open_run(spec, Path("pending"), {}) for _ in hexes]
    monkeypatch.undo()
    return ids


def test_ledger_rows_break_a_created_utc_tie_by_insertion(tmp_path,
                                                          monkeypatch):
    led = R.Ledger(tmp_path / "ledger.sqlite")
    # the older run gets the suffix that sorts FIRST, so id order would
    # put it first; the second opened must come back newest
    old, new = _open_same_second(monkeypatch, led, ["000000", "ffffff"],
                                 created=4_000_000_000.0)
    assert [r["run_id"] for r in led.rows()] == [new, old]
    old2, new2 = _open_same_second(monkeypatch, led, ["eeeeee", "111111"],
                                   created=4_000_000_001.0)
    assert [r["run_id"] for r in led.rows()][:2] == [new2, old2]
    assert [r["run_id"] for r in led.rows_mentioning("Ohio")][:2] == \
        [new2, old2]
    # the id format and its parsing are unchanged
    assert R.run_id_time(new2) == "2098-01-03 12:00"


def test_latest_results_is_the_run_started_last_in_the_same_second(
        tmp_path, monkeypatch):
    led = R.Ledger(tmp_path / "ledger.sqlite")
    # opened first, but its suffix sorts after the newer one's
    old, new = _open_same_second(monkeypatch, led, ["ffffff", "000000"])
    for rid in (old, new):
        w = tmp_path / "workroots" / rid
        w.mkdir(parents=True)
        (w / "results.json").write_text(json.dumps(
            {"forecast_date": "2098-01-03", "spec": "{}", "which": rid}))
    monkeypatch.setattr(R, "APP_STATE", tmp_path)
    shared._invalidate_scans()
    rid, res = shared._latest_results()
    assert rid == new and res["which"] == new
    assert [p.parent.name for p in shared._workroot_results()] == [new, old]
    shared._invalidate_scans()
