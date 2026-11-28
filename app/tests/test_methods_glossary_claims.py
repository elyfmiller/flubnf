"""Three of the console's words on Methods, held to what the code does
(review 3 of the usability work, P2-7 and P2-8; the cap), read from the
page the server renders (served_dom.tree).

  * P2-7, "Modified settings": a run is modified by a Model setting that
    changes a model (knobs.modified reads the model record alone). The
    settings Model settings tags "optional" only add rows and never count,
    and the line says so, so a forecaster need not leave Horizon -1 rows
    off for fear of non-hub file names.
  * P2-8, "Run ledger": the record of the runs made here. Storage's table
    shows the newest rows only, and clearing the ledger removes rows and
    leaves the runs' workroots on disk; the line says both, and never
    calls the table a list of every run.
  * "Upper-tail cap": only clip holds every quantile above the median to
    n times the level (flubnf/tailcap.py cap_block); shrink takes the
    power that brings the location's worst horizon's 97.5% quantile to
    the limit and applies it to the whole upper tail (exponent_needed,
    shrink_block), so the 99% quantile can stay above. The line says
    which form does what, and no longer holds every quantile to the limit
    whatever the form.
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
    """The Glossary card's line for `term`: its dd's words."""
    fold = [el for el in _flat(_methods())
            if el["attrs"].get("id") == "glossary"]
    assert len(fold) == 1
    els = _flat(fold[0])
    for i, el in enumerate(els):
        if el["tag"] == "dt" and _words(el) == term:
            dd = next(e for e in els[i + 1:] if e["tag"] == "dd")
            return _words(dd)
    raise AssertionError(f"no {term!r} in the glossary")


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


# ------------------------------------------------------ Upper-tail cap

def test_the_cap_line_says_what_each_form_holds():
    said = _said("Upper-tail cap")
    assert ("With clip each quantile above the median is held to that "
            "limit, never below the median") in said
    assert ("with shrink the location's whole upper tail is pulled in "
            "together until its worst horizon's 97.5% quantile meets the "
            "limit, so the 99% quantile can stay above it.") in said
    # no blanket ceiling on every quantile, whatever the form
    assert "each quantile above the median is held to at most" not in said
    assert "0 is no cap" in said and "Before cap" in said
    for dash in ("–", "—"):
        assert dash not in said


def _rows(sd_by_horizon: dict, median: float = 100.0) -> list:
    """Hub quantile rows for one location: a lognormal spread per horizon
    about one median, in whole admissions as the hub rows come."""
    from statistics import NormalDist

    from flubnf import tailcap as TC
    levels = [0.01, 0.025, *[round(0.05 * i, 2) for i in range(1, 20)],
              0.975, 0.99]
    z = NormalDist().inv_cdf
    return [{"target": TC.TARGET, "output_type": "quantile",
             "location": "10", "horizon": h, "output_type_id": q,
             "value": float(round(median * 2.718281828459045 ** (sd * z(q))))}
            for h, sd in sd_by_horizon.items() for q in levels]


def _block(rows: list, h: int) -> dict:
    return {r["output_type_id"]: r["value"] for r in rows if r["horizon"] == h}


def test_the_cap_line_matches_tailcap():
    """What the line leans on, in flubnf/tailcap.py: the limit 300 (n = 10
    on a level of 30) under a wide horizon 3 and a narrow horizon 0. Clip
    holds every level above the median at or under it; shrink brings
    horizon 3's 97.5% quantile to it, leaves its 99% above it, and pulls
    horizon 0 in by the same power though it was under the limit."""
    from flubnf import tailcap as TC
    rows = _rows({0: 0.3, 3: 0.8})
    lim = TC.limit_for(10, [30, 30, 30])
    assert lim == 300.0 and _block(rows, 3)[0.975] > lim
    clip, _ = TC.cap_rows(rows, {"10": lim}, mode="clip")
    for h in (0, 3):
        assert all(v <= lim for q, v in _block(clip, h).items() if q > 0.5), h
    shrink, _ = TC.cap_rows(rows, {"10": lim}, mode="shrink")
    s3, s0, r0 = _block(shrink, 3), _block(shrink, 0), _block(rows, 0)
    assert s3[0.975] == lim and s3[0.99] > lim
    assert s3[0.5] == _block(rows, 3)[0.5]
    assert r0[0.975] < lim and s0[0.975] < r0[0.975]
