"""The console run's honesty guards, pinned on the 2026-09-01 final pass.

Four field facts drive these tests:

  * a location whose PF replicates ALL failed used to ship an
    analogue-only forecast under the ensemble model name, silently; the
    retro store (app/core/retro.run_week) refuses a week with no PF at
    all and records partial failures beside the samples, and the console
    now mirrors both choices;
  * the first Windows full grid (2026-09-01) finished with 4 cell
    failures and NO page named the cells or reasons, so a student could
    not report the partial run usefully;
  * the forecast archive was replaced by rmtree-then-copy, so a crash or
    full disk mid-copy destroyed the previous archive for the date;
  * one unparseable value string in one state silenced the same-day
    under-reporting warning for every other state.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core.runs import Ledger, RunSpec            # noqa: E402
from app.core.submit import hub_model_id             # noqa: E402
from app.ui import server as srv                     # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL  # noqa: E402

client = TestClient(srv.app)

# wide, monotone member forecasts: every quantile set passes the writer's
# completeness, monotonicity and zero-width gates
SAMPLES = {str(h): [float(v) for v in np.linspace(10.0 * h, 60.0 * h, 40)]
           for h in (1, 2, 3, 4)}
AN_Q = {str(h): {float(L): 10.0 * h + 40.0 * h * float(L) for L in QL}
        for h in (1, 2, 3, 4)}


@pytest.fixture(autouse=True)
def _isolated_status():
    status_before = dict(srv._status)
    form_before = dict(srv._last_form)
    yield
    srv._status.clear(); srv._status.update(status_before)
    srv._last_form.clear(); srv._last_form.update(form_before)
    srv._invalidate_scans()


def _fake_run(monkeypatch, tmp_path, status_by_cell, collected):
    """Drive srv._run_all end to end with fake engines: PF cell statuses
    and collected samples are injected, the analogue answers for every
    location, scoring has no truth. Returns (ledger row, outcome dict,
    workroot path)."""
    import app.core.engines.analogue as an_engine
    import app.core.engines.pf as pf_engine
    import app.core.floor as floor_mod
    import app.core.scoring as scoring_mod
    import flubnf.settings as fs

    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    exe = tmp_path / "exe"
    exe.write_text("")
    monkeypatch.setattr(fs, "PY_ENGINE", exe)
    monkeypatch.setattr(fs, "PYBNF", exe)
    monkeypatch.setattr(pf_engine, "prepare", lambda spec, w: [])
    monkeypatch.setattr(pf_engine, "execute",
                        lambda w: dict(status_by_cell))
    monkeypatch.setattr(pf_engine, "collect",
                        lambda w: {loc: {h: list(v) for h, v in s.items()}
                                   for loc, s in collected.items()})
    monkeypatch.setattr(an_engine, "run",
                        lambda spec: {loc: {h: dict(q)
                                            for h, q in AN_Q.items()}
                                      for loc in spec.locations})
    monkeypatch.setattr(floor_mod, "floor_samples",
                        lambda s, loc, d, recent=None: s)
    monkeypatch.setattr(floor_mod, "floor_quantiles", lambda q: q)
    def _no_truth():
        raise RuntimeError("no truth in this test")
    monkeypatch.setattr(scoring_mod, "load_truth", _no_truth)
    monkeypatch.setattr(srv, "_sleep_guard", lambda: None)
    monkeypatch.setattr(srv, "_engine_versions_for_ledger", lambda e: {})
    monkeypatch.setattr(srv, "_harvest_params", lambda w: {})
    monkeypatch.setattr(srv, "_write_weekly_report",
                        lambda *a, **k: None)
    spec = RunSpec(engine="all", forecast_date="2098-01-04",
                   locations=["Ohio", "Texas"], replicates=1)
    srv._run_all(spec)
    row = next(iter(Ledger().rows(5)))
    outcome = json.loads(row.get("outcome") or "{}")
    return row, outcome, tmp_path / "workroots" / row["run_id"]


# ------------------------ a one-member blend never ships as the ensemble

def test_a_location_with_no_pf_member_is_recorded_not_silently_blended(
        tmp_path, monkeypatch):
    """Every Texas replicate fails, Ohio's succeeds. The retro precedent
    for a partial week is keep-and-record, so Texas stays in the ensemble
    file, and the outcome names it so the chips and the run page can say
    its cell is the analogue member alone."""
    row, outcome, w = _fake_run(
        monkeypatch, tmp_path,
        {"Ohio_r0": "ok", "Texas_r0": "error: fit failed"},
        {"Ohio": SAMPLES})
    assert row["status"] == "partial"
    assert outcome["ensemble_analogue_only"] == ["Texas"]
    assert "ensemble_withheld" not in outcome
    ens_id = hub_model_id("ensemble")
    assert ens_id in outcome["submissions"]
    csv = Path(outcome["submissions"][ens_id]).read_text()
    assert ",48," in csv                    # Texas (fips 48) still ships
    assert ",39," in csv                    # Ohio too
    chips = srv._outcome_chips(json.dumps(outcome))
    assert "1 location analogue-only in the ensemble" in chips


def test_all_pf_fits_failed_withholds_the_ensemble_file(
        tmp_path, monkeypatch):
    """Both locations fail, nothing is collected: the retro store refuses
    such a week outright (run_week raises rather than scoring
    analogue-alone cells as the ensemble), and the console mirrors that
    by withholding the ensemble CSV; an all-analogue file under the hub
    ensemble name is indistinguishable from the real blend."""
    row, outcome, w = _fake_run(
        monkeypatch, tmp_path,
        {"Ohio_r0": "error: fit failed", "Texas_r0": "error: fit failed"},
        {})
    assert "ensemble_withheld" in outcome
    assert hub_model_id("ensemble") not in outcome.get("submissions", {})
    assert not list(w.rglob("*.csv"))       # no PF file either: no samples
    assert "ensemble_analogue_only" not in outcome
    chips = srv._outcome_chips(json.dumps(outcome))
    assert "ensemble withheld: no PF member" in chips


# ----------------------------- the run page names cells and step errors

def test_run_page_names_failed_cells_and_step_errors(tmp_path, monkeypatch):
    """The chips only COUNT failures. The run page must name the cells,
    their statuses and every per-step error, plainly and escaped, so a
    partial run can be reported by copying the block (first Windows full
    grid, 2026-09-01: 4 failures, nothing visible anywhere)."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {})
    w = tmp_path / "workroots" / rid
    w.mkdir(parents=True)
    (w / "results.json").write_text(json.dumps({"models": {}}))
    led.close_run(rid, "partial", {
        "pf_cells": 159,
        "pf_failures": {"Texas_r1": "pybnf exited 1 <b>boom</b>",
                        "Maine_r0": "timeout after 3600 s"},
        "score_error": "truth file unreadable",
        "archive_error": "disk full",
        "report_inputs_error": "bundle too large",
        "ensemble_analogue_only": ["Texas"]})
    srv._invalidate_scans()
    html = client.get(f"/runs/{rid}").text
    assert "Partial-run detail" in html
    assert "Texas_r1" in html and "pybnf exited 1" in html
    assert "Maine_r0" in html and "timeout after 3600 s" in html
    assert "score_error" in html and "truth file unreadable" in html
    assert "archive_error" in html and "disk full" in html
    assert "report_inputs_error" in html and "bundle too large" in html
    assert "Analogue-only in the ensemble" in html
    # Jinja default escaping, no |safe: a status string cannot inject markup
    assert "<b>boom</b>" not in html
    assert "&lt;b&gt;boom&lt;/b&gt;" in html


def test_run_page_without_failures_shows_no_detail_block(tmp_path,
                                                         monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    rid = led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                       Path("pending"), {})
    (tmp_path / "workroots" / rid).mkdir(parents=True)
    led.close_run(rid, "ok", {"pf_cells": 2, "pf_failures": {}})
    srv._invalidate_scans()
    assert "Partial-run detail" not in client.get(f"/runs/{rid}").text


# --------------------------------- the archive swap is never a half-copy

def test_a_failed_archive_copy_keeps_the_previous_archive(tmp_path,
                                                          monkeypatch):
    """Beside, then swap: a copy that dies mid-way (ENOSPC here) must
    leave the previous archive for the date exactly as it was, with no
    half-built sibling; the next attempt then replaces it cleanly."""
    import shutil as shutil_mod
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "w"
    (w / "submission").mkdir(parents=True)
    (w / "results.json").write_text('{"new": true}')
    (w / "submission" / "f.csv").write_text("new-file")
    arch = tmp_path / "archive" / "2098-01-04"
    arch.mkdir(parents=True)
    (arch / "results.json").write_text('{"old": true}')
    real_copytree = shutil_mod.copytree
    def _enospc(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(shutil_mod, "copytree", _enospc)
    with pytest.raises(OSError):
        srv._archive_run(w, "2098-01-04")
    assert (arch / "results.json").read_text() == '{"old": true}'
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]
    monkeypatch.setattr(shutil_mod, "copytree", real_copytree)
    out = srv._archive_run(w, "2098-01-04")
    assert Path(out) == arch
    assert (arch / "results.json").read_text() == '{"new": true}'
    assert (arch / "submission" / "f.csv").read_text() == "new-file"
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]


def test_a_crash_between_the_two_renames_is_recovered(tmp_path,
                                                      monkeypatch):
    """The narrow window: the previous archive was parked aside and the
    process died before the replacement moved in. The next attempt must
    put the parked copy back FIRST, so a failure in that attempt still
    leaves the date with its previous record."""
    import shutil as shutil_mod
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "w"
    (w / "submission").mkdir(parents=True)
    (w / "results.json").write_text('{"new": true}')
    parked = tmp_path / "archive" / "2098-01-04.old"
    parked.mkdir(parents=True)
    (parked / "results.json").write_text('{"previous": true}')
    def _enospc(*a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(shutil_mod, "copytree", _enospc)
    arch = tmp_path / "archive" / "2098-01-04"
    with pytest.raises(OSError):
        srv._archive_run(w, "2098-01-04")
    assert (arch / "results.json").read_text() == '{"previous": true}'
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]


# ------------------- one poisoned row never silences the same-day warning

def test_one_poisoned_row_does_not_kill_the_underreporting_warning(
        tmp_path, monkeypatch):
    """Ohio's same-day count is under half its prior week (warn), Texas's
    value is an unparseable string (skip THAT ROW), California is fine.
    The warning must still fire for Ohio, and the log must record the
    skipped row; one odd value string used to silence the warning for
    every state (2026-09-01 final pass)."""
    monkeypatch.setattr(srv, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    vint = tmp_path / "v.csv"
    lines = ["date,location,location_name,value"]
    for fips, name, prior, same in (("39", "Ohio", "100", "30"),
                                    ("48", "Texas", "100", "oops"),
                                    ("06", "California", "100", "90")):
        lines.append(f"2097-12-28,{fips},{name},{prior}")
        lines.append(f"2098-01-04,{fips},{name},{same}")
    vint.write_text("\n".join(lines) + "\n")
    monkeypatch.setattr(srv.data_mod, "vintage_path", lambda d: vint)
    monkeypatch.setattr(srv, "_run_all", lambda spec: None)
    r = client.post("/run", data={"forecast_date": "2098-01-04",
                                  "locations": ["Ohio"]},
                    follow_redirects=False)
    assert r.status_code == 303
    flash = srv._status.get("flash") or ""
    assert "under-reported" in flash
    assert "Ohio" in flash and "1 state(s)" in flash
    assert "California" not in flash
    assert any("same-day" in m and "skipped" in m
               for m in srv._status["log"])
