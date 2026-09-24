"""The particle filter's fit origin when the newest week(s) are unreported.

resolve_state (flubnf/sihrs_fit.py) drops an unreported week as a row and
keeps the true offsets, so a trailing unreported week moves the fit origin
back. app/core/engines/pf.py counts it like a dropped week: the forecast
intervals (4 + lag) and collect()'s horizon shift both use the weeks
between the origin and the as-of week, so horizon h stays as-of + 7h, the
way the Groundhog's anchor does (app/core/engines/analogue.py _walk). More
than MAX_ANCHOR_LAG unreported weeks beyond the requested trims and the
location abstains with the reason recorded. The hub data never has such a
week; a user's dataset (app/core/datasets.py) can, so the fixture here is a
small dataset whose newest row is missing for one group.

Held: a complete series prepares exactly as before (no note, no notes
file, 4 intervals); a missing newest week prepares the same cell as
weeks_to_drop = 1 on the complete series; the Groundhog anchors on the
same week and says the same thing; the Oracle step reads the same k; the
run page shows both members' notes in one row.
"""
from __future__ import annotations

import json
import re
import types
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.core import custom_run as CR
from app.core import datasets as D
from app.core import horizons as hz
from app.core import oracle as oracle_mod
from app.core import runs as R
from app.core.engines import analogue as EA
from app.core.engines import pf as PF
from app.core.runs import RunSpec

from test_dataset_engines import grouped_bytes          # noqa: E402
from test_oracle_step import ASOF, console, hubfiles    # noqa: E402,F401

FD = "2023-12-02"                   # the fixture's newest week (a Saturday)
GROUPS = ("Pediatric", "Adult")


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(D, "ROOT", tmp_path / "datasets")
    return tmp_path / "datasets"


@pytest.fixture
def netgen(monkeypatch):
    """prepare() for real (resolve_state, materialize, write_exp) with
    BNG2.pl faked to write m.net and Perl present."""
    monkeypatch.setattr(PF, "perl_available", lambda: True)

    def fake_netgen(cmd, **kw):
        (Path(kw.get("cwd", ".")) / "m.net").write_text("# net\n")
        return types.SimpleNamespace(stdout="", stderr="", returncode=0)
    monkeypatch.setattr(PF.subprocess, "run", fake_netgen)


def dataset(unreported: int = 0, name: str = "wave"):
    """Pediatric and Adult through FD; Adult's newest `unreported` rows
    deleted (a dataset leaves an unreported week out)."""
    lines = grouped_bytes(groups=GROUPS, end=date(2023, 12, 2)).decode(
    ).strip().split("\n")
    adult = [i for i, ln in enumerate(lines) if ",Adult," in ln]
    for i in sorted(adult[len(adult) - unreported:], reverse=True):
        del lines[i]
    return D.ingest(("\n".join(lines) + "\n").encode(), name, kind="count")


def spec(ds, weeks_to_drop=0, engine="pf", **kw):
    return RunSpec(engine=engine, forecast_date=FD, locations=list(GROUPS),
                   weeks_to_drop=weeks_to_drop, replicates=1, particles=100,
                   extra={"dataset": ds.ref(), "oracle": "none",
                          **kw.pop("extra", {})}, **kw)


def by_loc(cells):
    return {c["location"]: c for c in cells}


def conf(cell):
    return (Path(cell["dir"]) / "pf.conf").read_text()


def exp(cell):
    return next(Path(cell["dir"]).glob("*.exp")).read_text()


# --- the shipped path: a complete series prepares exactly as before ----------

#: the cell record's keys before this change (a complete series adds none)
SHIPPED_KEYS = {
    "key", "dir", "location", "replicate", "seed", "weeks_dropped", "variant",
    "a0", "typed_weeks", "iota", "natg_last_gap", "natg_active_weeks",
    "natg_clipped_weeks", "n_obs", "last_week_offset", "seed_date",
    "initialization", PF.SAMPLING_INTERVAL_KEY, "pf_keys", "prior_ranges",
    "anchor_asof", "i0", "fit_i0", "reporting", "state_file",
    "continued_from", "save_state_to", "particles", "last_observed"}


def test_a_complete_series_prepares_as_before(netgen, tmp_path):
    ds = dataset()
    w = tmp_path / "w"
    cells = by_loc(PF.prepare(spec(ds), w))
    for c in cells.values():
        assert set(c) == SHIPPED_KEYS
        assert c["weeks_dropped"] == 0
        assert "pf_forecast_intervals = 4\n" in conf(c)
    assert not (w / PF.ANCHOR_NOTES_NAME).exists()
    assert PF.read_anchor_notes(w) == {}
    assert PF.read_prepare_failures(w) == {}


def test_a_trim_on_a_complete_series_is_unchanged(netgen, tmp_path):
    ds = dataset()
    cells = by_loc(PF.prepare(spec(ds, weeks_to_drop=1), tmp_path / "w"))
    for c in cells.values():
        assert c["weeks_dropped"] == 1 and "anchor_note" not in c
        assert "pf_forecast_intervals = 5\n" in conf(c)
    assert not (tmp_path / "w" / PF.ANCHOR_NOTES_NAME).exists()


# --- a trailing unreported week counts like a dropped week --------------------

def test_an_unreported_newest_week_counts_like_a_dropped_week(netgen, tmp_path):
    gap = by_loc(PF.prepare(spec(dataset(unreported=1)), tmp_path / "gap"))
    a = gap["Adult"]
    assert a["weeks_dropped"] == 1
    assert a["anchor_note"] == "anchored on 2023-11-25: 1 newer week(s) unreported"
    assert "pf_forecast_intervals = 5\n" in conf(a)
    assert PF.read_anchor_notes(tmp_path / "gap") == {"Adult": a["anchor_note"]}
    # the reported group is untouched
    p = gap["Pediatric"]
    assert p["weeks_dropped"] == 0 and "anchor_note" not in p
    assert "pf_forecast_intervals = 4\n" in conf(p)
    # ... and Adult is the cell weeks_to_drop = 1 prepares on the full series
    full = by_loc(PF.prepare(spec(dataset(name="full"), weeks_to_drop=1),
                             tmp_path / "full"))["Adult"]
    for k in ("weeks_dropped", "n_obs", "last_week_offset", "last_observed",
              "i0", "seed"):
        assert a[k] == full[k], k
    assert exp(a) == exp(full)
    assert (conf(a).replace(str(tmp_path / "gap"), "W")
            == conf(full).replace(str(tmp_path / "full"), "W"))


def test_two_unreported_weeks_on_top_of_a_trim(netgen, tmp_path):
    cells = by_loc(PF.prepare(spec(dataset(unreported=2), weeks_to_drop=1),
                              tmp_path / "w"))
    a = cells["Adult"]
    # rows through 2023-11-25 reported ... one trimmed; 11-25 and 12-02
    # unreported: the origin is 11-11, three weeks before the as-of
    assert a["weeks_dropped"] == 3
    assert a["anchor_note"] == "anchored on 2023-11-11: 2 newer week(s) unreported"
    assert "pf_forecast_intervals = 7\n" in conf(a)
    assert cells["Pediatric"]["weeks_dropped"] == 1


def test_past_two_unreported_weeks_the_location_abstains(netgen, tmp_path):
    w = tmp_path / "w"
    cells = by_loc(PF.prepare(spec(dataset(unreported=3)), w))
    assert set(cells) == {"Pediatric"}           # the other group still runs
    fail = PF.read_prepare_failures(w)[PF.dataset_tag("Adult")]
    assert fail.startswith("FAIL: prepare: Adult: abstained: newest reported "
                           "week 2023-11-11 is 3 weeks before 2023-12-02")
    assert PF.read_anchor_notes(w) == {
        "Adult": "abstained: newest reported week 2023-11-11 is 3 weeks "
                 "before the as-of"}


def test_a_single_abstaining_location_says_why(netgen, tmp_path):
    ds = dataset(unreported=3)
    with pytest.raises(ValueError, match="Adult: abstained"):
        PF.prepare(RunSpec(engine="pf", forecast_date=FD, locations=["Adult"],
                           replicates=1, particles=100,
                           extra={"dataset": ds.ref()}), tmp_path / "w")


# --- the horizons: collect() maps the extended forecast to the as-of ----------

def _write_trajectories(workroot: Path) -> dict:
    """Each cell's trajectory as the engine writes it (a column per .exp row,
    then pf_forecast_intervals weekly columns), holding the column's true
    week offset times `unit`, so the origin column carries last_observed
    exactly and collect() scales by 1. Returns {location: unit}."""
    units = {}
    for c in json.loads((workroot / "cells.json").read_text()):
        rows = [ln.split() for ln in exp(c).splitlines()[1:]]
        t = [int(r[0]) for r in rows]
        k = int(re.search(r"pf_forecast_intervals = (\d+)", conf(c)).group(1))
        offs = t + [t[-1] + i for i in range(1, k + 1)]
        unit = c["last_observed"] / t[-1]
        runs = Path(c["dir"]) / "out" / "Results" / "PF" / "Runs"
        runs.mkdir(parents=True)
        np.savetxt(runs / "x_traj_noise.txt",
                   np.tile(np.asarray(offs, float) * unit, (2, 1)))
        units[c["location"]] = unit
    return units


def test_collect_counts_horizons_from_the_as_of_week(netgen, tmp_path):
    w = tmp_path / "w"
    PF.prepare(spec(dataset(unreported=1)), w)
    units = _write_trajectories(w)
    got = PF.collect(w)
    asof = (date.fromisoformat(FD) - date.fromisoformat(
        RunSpec(engine="pf", forecast_date=FD).season_start)).days // 7
    for loc in GROUPS:
        u = units[loc]
        assert got[loc][hz.ORIGIN][0] == pytest.approx(asof * u)
        for h in hz.HORIZONS:          # hub horizon h is physical week h + 1
            assert got[loc][h][0] == pytest.approx((asof + int(h) + 1) * u), (
                loc, h)


# --- the Groundhog and the Oracle step read the anchor the same way ----------

@pytest.mark.parametrize("unreported, drop", [(1, 0), (2, 1), (3, 0)])
def test_the_groundhog_anchors_on_the_same_week(netgen, tmp_path,
                                                unreported, drop):
    ds = dataset(unreported=unreported)
    w = tmp_path / "w"
    PF.prepare(spec(ds, weeks_to_drop=drop), w)
    notes = {}
    EA.run(spec(ds, weeks_to_drop=drop, engine="analogue"), notes=notes)
    assert notes == PF.read_anchor_notes(w)


def test_a_flagged_week_is_dated_as_the_groundhog_dates_it(netgen, tmp_path):
    """The default season start (August 1) is not a Saturday: the filter's
    flagged week is the data week, the date the Groundhog records."""
    lines = grouped_bytes(groups=GROUPS, end=date(2023, 12, 2)).decode(
    ).strip().split("\n")
    i = max(j for j, ln in enumerate(lines) if ",Adult," in ln)
    lines[i] = re.sub(r",Adult,[^,]*", ",Adult,0", lines[i])
    ds = D.ingest(("\n".join(lines) + "\n").encode(), "zero", kind="count")
    on = {"knobs": {"data.trailing_zero": "missing"}}
    cells = by_loc(PF.prepare(spec(ds, extra=on), tmp_path / "w"))
    gh = []
    EA.run(spec(ds, engine="analogue", extra=on), flags=gh)
    assert cells["Adult"]["data_flags"] == [
        {"week": FD, "rule": "trailing zero", "value": 0.0}]
    assert gh == [{"location": "Adult", "week": FD, "rule": "trailing zero",
                   "value": 0.0}]
    assert "anchor_note" not in cells["Adult"]     # a flag, not a gap


def test_the_oracle_step_reads_the_lag_as_k(netgen, tmp_path):
    w = tmp_path / "w"
    PF.prepare(spec(dataset(unreported=1)), w)
    assert oracle_mod.weeks_dropped(w) == {"Pediatric": 0, "Adult": 1}


# --- recorded with the run and shown on its page ------------------------------

def _fake_execute(workroot):
    workroot = Path(workroot)
    _write_trajectories(workroot)
    return {c["key"]: "ok"
            for c in json.loads((workroot / "cells.json").read_text())}


def test_a_dataset_run_records_both_members_notes(netgen, tmp_path,
                                                  monkeypatch):
    ds = dataset(unreported=1)
    monkeypatch.setattr(PF, "execute", _fake_execute)
    w = tmp_path / "w"
    w.mkdir()
    s = RunSpec(engine="all", forecast_date=FD, locations=list(GROUPS),
                replicates=1, particles=100,
                extra={"dataset": ds.ref(), "oracle": "none",
                       "dataset_final": True})
    outcome, fails = CR.run(s, ds, w, pf_state="ready")
    note = "anchored on 2023-11-25: 1 newer week(s) unreported"
    assert fails == {}
    assert outcome["pf_anchor_notes"] == {"Adult": note}
    assert outcome["analogue_anchor_notes"] == {"Adult": note}
    assert "data_flags" not in outcome           # no missing-data rule on
    html = R.results_html(outcome, s.to_json())
    assert "Unreported newest weeks" in html
    assert ("plain SIHRS particle filter: 1 location anchored earlier; "
            f"{R.GROUNDHOG_OWN_DATA}: 1 location anchored earlier") in html
    assert f"Adult: {note}." in html


def test_a_complete_dataset_run_records_no_notes(netgen, tmp_path,
                                                 monkeypatch):
    ds = dataset()
    monkeypatch.setattr(PF, "execute", _fake_execute)
    w = tmp_path / "w"
    w.mkdir()
    s = RunSpec(engine="all", forecast_date=FD, locations=list(GROUPS),
                replicates=1, particles=100,
                extra={"dataset": ds.ref(), "oracle": "none",
                       "dataset_final": True})
    outcome, _ = CR.run(s, ds, w, pf_state="ready")
    assert "pf_anchor_notes" not in outcome
    assert "analogue_anchor_notes" not in outcome
    assert "Unreported newest weeks" not in R.results_html(outcome, s.to_json())


def test_the_hub_run_page_shows_both_notes_in_one_row():
    o = {"pf_anchor_notes": {"Ohio": "anchored on 2026-01-03: 1 newer week(s) "
                                     "unreported"},
         "analogue_anchor_notes": {
             "Ohio": "anchored on 2026-01-03: 1 newer week(s) unreported",
             "Utah": "abstained: newest reported week 2025-12-20 is 3 weeks "
                     "before the as-of"}}
    spec_json = RunSpec(engine="all", forecast_date="2026-01-10",
                        locations=["Ohio", "Utah"]).to_json()
    html = R.results_html(o, spec_json)
    assert html.count("Unreported newest weeks") == 1
    assert ("Oracle SIHRS: 1 location anchored earlier; Groundhog: 1 "
            "location anchored earlier, 1 abstained") in html
    assert "Groundhog, Utah: abstained: newest reported week 2025-12-20" in html
    # a run without notes (every shipped run on the hub's data) has no row
    assert "Unreported newest weeks" not in R.results_html({}, spec_json)


def test_the_console_run_records_the_filters_notes(console, monkeypatch):
    """The console pipeline keeps prepare()'s notes as pf_anchor_notes,
    beside the Groundhog's analogue_anchor_notes, and the run page shows
    them; a run whose prepare wrote none carries no key."""
    from app.ui import pipeline as ui_pipeline
    note = "anchored on 2098-01-03: 1 newer week(s) unreported"

    def fake_prepare(spec, w):
        Path(w).mkdir(parents=True, exist_ok=True)
        (Path(w) / PF.ANCHOR_NOTES_NAME).write_text(json.dumps({"Utah": note}))
        return []
    monkeypatch.setattr(PF, "prepare", fake_prepare)
    s = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                extra={"mode": "vintage"})
    ui_pipeline._run_all(s)
    out = json.loads(R.Ledger().rows(1)[0]["outcome"])
    assert out["pf_anchor_notes"] == {"Utah": note}
    assert "Oracle SIHRS: 1 location anchored earlier" in R.results_html(
        out, s.to_json())
    monkeypatch.setattr(PF, "prepare", lambda spec, w: [])
    ui_pipeline._run_all(s)
    assert "pf_anchor_notes" not in json.loads(
        R.Ledger().rows(1)[0]["outcome"])
