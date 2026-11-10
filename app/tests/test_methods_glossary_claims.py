"""Two of the console's words on Methods, held to what the code does
(review 3 of the usability work, P2-7 and P2-8), read from the page the
server renders (served_dom.tree).

  * P2-7, "Modified settings": a run is modified by a Model setting that
    changes a model (knobs.modified reads the model record alone). The
    settings Model settings tags "optional" only add rows and never count,
    and the line says so, so a forecaster need not leave Horizon -1 rows
    off for fear of non-hub file names.
  * P2-8, "Run ledger": the record of the runs made here. Storage's table
    shows the newest rows only, and clearing the ledger removes rows and
    leaves the runs' workroots on disk; the line says both, and never
    calls the table a list of every run.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.core import knobs
from app.ui.routes import storage as storage_routes
from app.ui.server import app as srv

import served_dom as SD                                  # noqa: E402

client = TestClient(srv)


def _flat(node, out=None):
    out = [] if out is None else out
    for k in node["kids"]:
        if not isinstance(k, str):
            out.append(k)
            _flat(k, out)
    return out


def _text(node) -> str:
    if isinstance(node, str):
        return node
    return "".join(_text(k) for k in node["kids"])


def _words(node) -> str:
    return " ".join(_text(node).split())


def _methods():
    r = client.get("/methods")
    assert r.status_code == 200, r.text[:300]
    return SD.tree(r.text)


def _said(term: str) -> str:
    """The Words used here line for `term`: its dd's words."""
    fold = [el for el in _flat(_methods())
            if el["attrs"].get("id") == "mt-words"]
    assert len(fold) == 1
    els = _flat(fold[0])
    for i, el in enumerate(els):
        if el["tag"] == "dt" and _words(el) == term:
            dd = next(e for e in els[i + 1:] if e["tag"] == "dd")
            return _words(dd)
    raise AssertionError(f"no {term!r} in the fold")


def _spec(rec: dict) -> str:
    return json.dumps({"extra": {knobs.RECORD_KEY: rec}})


# --------------------------------------------- P2-7: Modified settings

def test_modified_settings_says_an_optional_setting_never_counts():
    said = _said("Modified settings")
    assert "other than one tagged optional" in said
    assert "those only add rows" in said
    assert "any Model setting" not in said
    # the rest of the line as it was: the non-hub names and the override
    assert "<hub id>-modified" in said
    assert "unless exported under the hub names with a reason" in said
    for dash in ("–", "—"):
        assert dash not in said


def test_the_optional_tag_marks_exactly_the_settings_that_never_count():
    """What the line leans on: Model settings tags "optional" on the
    settings knobs.modified leaves out, each one adds rows and keeps the
    hub names, and a model setting off its default does count."""
    root = _methods()
    tagged = set()
    for row in _flat(root):
        if row["tag"] == "tr" and row["attrs"].get("id", "").startswith(
                "set-"):
            th = next(k for k in row["kids"]
                      if isinstance(k, dict) and k["tag"] == "th")
            if any("optional" == _words(t) for t in _flat(th)
                   if "uk-tag" in t["attrs"].get("class", "")):
                tagged.add(row["attrs"]["id"])
    want = {"set-" + k.replace(".", "-") for k in knobs.OPTIONAL_KEYS}
    assert want and tagged == want
    for key in knobs.OPTIONAL_KEYS:
        default = knobs.BY_KEY[key].default
        spec = _spec({key: not default})
        assert not knobs.modified(spec), key
        assert knobs.hub_names(spec), key
    assert knobs.modified(_spec({"oracle.w": 0.25}))


# --------------------------------------------------- P2-8: Run ledger

def test_run_ledger_says_the_table_is_capped_and_clearing_keeps_folders():
    said = _said("Run ledger")
    assert "every run" not in said
    assert said.startswith("The record of the runs made on this computer")
    assert "The Storage tab's table shows the newest rows only." in said
    assert ("Clearing the ledger removes its rows and leaves the runs' "
            "workroots on disk.") in said
    assert "the run can be reproduced from its row" in said


def test_the_ledger_line_matches_storage(tmp_path, monkeypatch):
    """The two facts the line states, on Storage itself: the table holds
    LEDGER_ROWS rows and says so past that, and the clear leaves each
    run's workroot where it was."""
    from pathlib import Path

    from app.core import runs as runs_mod
    from app.core.runs import Ledger, RunSpec
    from app.ui import shared
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    monkeypatch.setattr(storage_routes, "LEDGER_ROWS", 2)
    shared._invalidate_scans()
    try:
        led = Ledger()
        ids = []
        for _ in range(3):
            rid = led.open_run(RunSpec(engine="all",
                                       forecast_date="2098-01-03"),
                               Path("pending"), {})
            led.close_run(rid, "ok", {})
            (tmp_path / "workroots" / rid).mkdir(parents=True)
            ids.append(rid)
        page = client.get("/storage").text
        assert "Showing the newest 2 of 3 runs." in page
        r = client.post("/runs/clear", data={"confirm": "3"},
                        follow_redirects=False)
        assert r.status_code == 303
        assert led.rows(10) == []
        for rid in ids:
            assert (tmp_path / "workroots" / rid).is_dir(), rid
    finally:
        shared._invalidate_scans()
