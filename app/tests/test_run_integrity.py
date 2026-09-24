"""The console run's honesty guards.

  * a location whose PF replicates all failed is absent from the Oracle
    SIHRS file (never shipped under another model's name), and the row is
    partial;
  * the run page names failed cells and step errors, escaped;
  * the forecast archive is replaced beside-then-swap, never rmtree-then-
    copy, so a crash keeps the previous archive;
  * the same-day under-reporting heads-up is retired.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                     # noqa: E402
from app.core import data as core_data               # noqa: E402
from app.core.runs import Ledger, RunSpec            # noqa: E402
from app.core.submit import hub_model_id             # noqa: E402
from app.ui import server as srv                     # noqa: E402
from app.ui.routes import forecast as ui_forecast    # noqa: E402
from app.ui import pipeline as ui_pipeline           # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import shared as ui_shared               # noqa: E402
from app.ui import state as ui_state                 # noqa: E402
from app.ui import versions as ui_versions           # noqa: E402
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
    status_before = dict(ui_state._status)
    form_before = dict(ui_state._last_form)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


def _fake_run(monkeypatch, tmp_path, status_by_cell, collected, aux=None):
    """Drive srv._run_all end to end with fake engines (injected PF statuses
    and samples, an analogue for every location, no truth). `aux` is the
    Groundhog donor choice (None: shipped bank, "": bare analogue). Returns
    (ledger row, outcome, workroot)."""
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
    import app.core.oracle as oracle_mod
    # the Oracle step needs a vintage this hub-free test lacks: stub it
    monkeypatch.setattr(oracle_mod, "apply_week",
                        lambda s, asof, wd, **kw: (s, {"applied": True,
                                                       "bank": {"label": "stub"}}))
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
    monkeypatch.setattr(ui_pipeline, "_sleep_guard", lambda: None)
    monkeypatch.setattr(ui_versions, "_engine_versions_for_ledger", lambda e: {})
    monkeypatch.setattr(ui_pipeline, "_harvest_params", lambda w: {})
    monkeypatch.setattr(ui_pipeline, "_write_weekly_report",
                        lambda *a, **k: None)
    spec = RunSpec(engine="all", forecast_date="2098-01-04",
                   locations=["Ohio", "Texas"], replicates=1,
                   extra=ui_forecast._run_extra(2, "realtime", aux))
    ui_pipeline._run_all(spec)
    row = next(iter(Ledger().rows(5)))
    outcome = json.loads(row.get("outcome") or "{}")
    return row, outcome, tmp_path / "workroots" / row["run_id"]


# ------------------------ two standalone files, each honest on its own

def test_a_location_with_no_pf_member_is_absent_from_the_sihrs_file_only(
        tmp_path, monkeypatch):
    """Every Texas replicate fails: the Oracle SIHRS file holds Ohio alone,
    the Groundhog file holds both, the row is partial; no blend keys."""
    row, outcome, w = _fake_run(
        monkeypatch, tmp_path,
        {"Ohio_r0": "ok", "Texas_r0": "error: fit failed"},
        {"Ohio": SAMPLES})
    assert row["status"] == "partial"
    assert "ensemble_analogue_only" not in outcome
    assert "ensemble_withheld" not in outcome
    pf_id, gh_id = hub_model_id("pf"), hub_model_id("analogue")
    assert set(outcome["submissions"]) == {pf_id, gh_id}
    pf_csv = Path(outcome["submissions"][pf_id]).read_text()
    assert ",39," in pf_csv and ",48," not in pf_csv
    gh_csv = Path(outcome["submissions"][gh_id]).read_text()
    assert ",39," in gh_csv and ",48," in gh_csv
    assert outcome["analogue_aux"].startswith("flusurv+flusurv@")
    chips = ui_shared._outcome_chips(json.dumps(outcome))
    assert "analogue-only" not in chips and "withheld" not in chips


def test_all_pf_fits_failed_still_ships_the_groundhog(
        tmp_path, monkeypatch):
    """All PF fits fail: only the Oracle SIHRS file is lost; the Groundhog
    still writes under its own name."""
    row, outcome, w = _fake_run(
        monkeypatch, tmp_path,
        {"Ohio_r0": "error: fit failed", "Texas_r0": "error: fit failed"},
        {})
    assert "ensemble_withheld" not in outcome
    assert hub_model_id("pf") not in outcome.get("submissions", {})
    assert set(outcome["submissions"]) == {hub_model_id("analogue")}
    csvs = list(w.rglob("*.csv"))
    assert len(csvs) == 1 and csvs[0].parent.name == hub_model_id("analogue")


def test_the_bare_analogue_never_ships_under_the_groundhogs_name(
        tmp_path, monkeypatch):
    """With no auxiliary pools the analogue is the bare calendar analogue,
    not the Groundhog: its quantiles are kept, its file withheld with the
    reason on the row."""
    row, outcome, w = _fake_run(
        monkeypatch, tmp_path, {"Ohio_r0": "ok", "Texas_r0": "ok"},
        {"Ohio": SAMPLES, "Texas": SAMPLES}, aux="")
    assert set(outcome["submissions"]) == {hub_model_id("pf")}
    assert "bare calendar analogue" in outcome["submission_withheld"]
    assert outcome["analogue_aux"] == ""
    res = json.loads((w / "results.json").read_text())
    assert set(res["models"]) == {"pf", "analogue"}
    chips = ui_shared._outcome_chips(json.dumps(outcome))
    assert "submission withheld" in chips


# ----------------------------- the run page names cells and step errors

def test_run_page_names_failed_cells_and_step_errors(tmp_path, monkeypatch):
    """The run page names each failed cell, its status and every step error,
    escaped, so a partial run can be reported by copying the block."""
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
    ui_shared._invalidate_scans()
    html = client.get(f"/runs/{rid}").text
    assert "Partial-run detail" in html
    assert "Texas_r1" in html and "pybnf exited 1" in html
    assert "Maine_r0" in html and "timeout after 3600 s" in html
    assert "score_error" in html and "truth file unreadable" in html
    assert "archive_error" in html and "disk full" in html
    assert "report_inputs_error" in html and "bundle too large" in html
    # an older row's retired-blend key is read without error and not shown
    assert "Analogue-only in the ensemble" not in html
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
    ui_shared._invalidate_scans()
    assert "Partial-run detail" not in client.get(f"/runs/{rid}").text


# --------------------------------- the archive swap is never a half-copy

def test_a_failed_archive_copy_keeps_the_previous_archive(tmp_path,
                                                          monkeypatch):
    """A copy that dies mid-way (ENOSPC) leaves the previous archive intact
    with no half-built sibling; the next attempt replaces it cleanly."""
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
        ui_pipeline._archive_run(w, "2098-01-04")
    assert (arch / "results.json").read_text() == '{"old": true}'
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]
    monkeypatch.setattr(shutil_mod, "copytree", real_copytree)
    out = ui_pipeline._archive_run(w, "2098-01-04")
    assert Path(out) == arch
    assert (arch / "results.json").read_text() == '{"new": true}'
    assert (arch / "submission" / "f.csv").read_text() == "new-file"
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]


def test_a_crash_between_the_two_renames_is_recovered(tmp_path,
                                                      monkeypatch):
    """A crash between the two renames: the next attempt restores the parked
    copy FIRST, so its own failure still leaves the previous record."""
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
        ui_pipeline._archive_run(w, "2098-01-04")
    assert (arch / "results.json").read_text() == '{"previous": true}'
    assert sorted(p.name for p in arch.parent.iterdir()) == ["2098-01-04"]


# ------------------- the same-day under-reporting heads-up is gone

def test_no_underreporting_headsup_on_run(tmp_path, monkeypatch):
    """No same-day under-reporting warning (retired: its remedy cost 0.24
    relWIS and was never used), and the vintage is not read for it."""
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    vint = tmp_path / "v.csv"
    vint.write_text("date,location,location_name,value\n"
                    "2097-12-28,39,Ohio,100\n2098-01-04,39,Ohio,30\n")
    reads = []
    monkeypatch.setattr(core_data, "vintage_path",
                        lambda d: reads.append(d) or vint)
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: None)
    r = client.post("/run", data={"forecast_date": "2098-01-04",
                                  "locations": ["Ohio"]},
                    follow_redirects=False)
    assert r.status_code == 303
    flash = ui_state._status.get("flash") or ""
    assert "under-reported" not in flash and "Heads up" not in flash
    assert not any("same-day" in m for m in ui_state._status["log"])
