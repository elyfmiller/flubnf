"""The model knobs reach the models (Stage 2 of app/core/knobs.py).

What is held here:
  * a run with no knob touched is byte-identical to before: the same spec
    JSON, the same files, no knobs record anywhere;
  * the form's knob fields and the older field names are one channel,
    checked before the engine is claimed (a refusal starts nothing);
  * a modified run exports under the non-hub name unless the operator
    overrides with a reason, which is recorded with the run;
  * a ledger row from before the registry is never marked modified;
  * a retrospective tree holds one configuration: a resume with other
    knobs is refused, by the route, run_season and the CLI.

No hub and no engine: the console fixture of test_oracle_step fakes the
filter and the Groundhog and runs the real Oracle step on a tiny vintage.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.runs as runs_mod                             # noqa: E402
from app.core import knobs as K                              # noqa: E402
from app.core import oracle as oracle_mod                    # noqa: E402
from app.core import horizons as hz                       # noqa: E402
from app.core import retro                                   # noqa: E402
from app.core.engines import analogue as EA                  # noqa: E402
from app.core.runs import Ledger, RunSpec, spec_settings     # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui.routes import forecast as ui_forecast            # noqa: E402
from app.ui.routes import retro as ui_retro                  # noqa: E402
from app.ui import pipeline as ui_pipeline                   # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons         # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from app.ui.routes import output as ui_output                # noqa: E402

from test_oracle_step import (ASOF, _samples, console,       # noqa: E402,F401
                              hubfiles)

client = TestClient(srv.app)
FD = "2098-01-04"                                  # a Saturday


@pytest.fixture(autouse=True)
def _isolated():
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    retro_before = dict(ui_retro_seasons._retro_status)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_retro_seasons._retro_status.clear(); ui_retro_seasons._retro_status.update(retro_before)
    ui_shared._invalidate_scans()


def _capture_run(monkeypatch, tmp_path):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path / "retro")
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    # the real module, not the lazy proxy (its first use rebinds the name)
    import app.core.data as data
    monkeypatch.setattr(ui_state, "data_mod", data)
    monkeypatch.setattr(data, "vintage_path", lambda d: tmp_path)
    monkeypatch.setattr(data, "vintages", lambda: [FD])
    started = []
    monkeypatch.setattr(ui_pipeline, "_run_all", lambda spec: started.append(spec))
    return started


def _post(data):
    ui_state._status["running"] = None
    return client.post("/run", data={"forecast_date": FD,
                                     "locations": ["Ohio"], **data},
                       follow_redirects=False)


# --- the default is byte-identical -----------------------------------------------

#: what the default Forecast form ran before the knobs, as JSON (golden)
GOLDEN_EXTRA = {"mode": "realtime",
                "aux_pools": [{"stream": "flusurv", "weight": 0.5,
                               "committed": True}],
                # the Groundhog's own-state weighting, recorded since
                # 2026-10-15, with the size-matched kernel since 2026-10-23
                "local_pools": {"own_share": 0.5, "anchor_weight": "kernel",
                                "kernel_sd": 1.0, "ess_floor": 30.0}}


def test_the_untouched_form_runs_the_golden_shipped_spec(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    # the panel posts every knob blank, the older fields at their values
    blank = {f"knob.{k.key}": "" for k in K.REGISTRY
             if k.key not in K.FIELD_OF}
    r = _post({"particles": "", "replicates": "3", "season_start": "",
               "weeks_to_drop": "0", "drop_same_day": "", **blank,
               "submit_modified": "", "modified_reason": ""})
    assert r.status_code == 303 and len(started) == 1, ui_state._status.get("flash")
    spec = started[0]
    golden = {"drop_same_day": False, "engine": "all",
              "extra": {**GOLDEN_EXTRA,
                        "analogue_aux": EA.shipped_aux_label()},
              "forecast_date": FD, "jitter": 0.15,
              "locations": spec.locations, "particles": 10_000,
              "replicates": 3, "season_start": "2097-08-01",
              "weeks_to_drop": 0, "weeks_to_nowcast": 0}
    assert spec.to_json() == json.dumps(golden, sort_keys=True)
    assert not runs_mod.is_modified(spec)
    assert "model settings" not in dict(spec_settings(spec))
    # the default form without any knob field reads the same
    _post({})
    assert started[1].to_json() == spec.to_json()


def test_a_shipped_console_run_writes_what_it_always_wrote(console):
    srv_, raw = console
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                   extra=ui_forecast._run_extra(2, "vintage"))
    ui_pipeline._run_all(spec)
    row = Ledger().rows(1)[0]
    out = json.loads(row["outcome"])
    w = runs_mod.APP_STATE / "workroots" / row["run_id"]
    assert set(out["submissions"]) == {"NAU_PyBNF-OracleSIHRS",
                                       "NAU_PyBNF-GroundHogCGR"}
    assert "knobs" not in out and out["archived"] == "archived"
    assert not (w / "knobs.json").exists()
    res = json.loads((w / "results.json").read_text())
    # plus the recorded horizon convention (every run writes it, knobs or
    # not): still no knobs key on a shipped run
    assert set(res) == {"spec", "forecast_date", "research", "oracle",
                        "observed", "params", "models",
                        "horizon_convention"}
    prov = oracle_mod.read_provenance(w)
    assert "knobs" not in prov and "specification" not in prov
    assert prov["w"] == 0.5 and prov["bank"]["mixture"]["w_aux_nominal"] == 0.5


# --- the form channel --------------------------------------------------------------

def test_knob_fields_reach_the_spec_and_the_record(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    r = _post({"particles": "2000", "knob.pf.jitter": "0.3",
               "knob.pf.prior.r": "0.1, 80", "knob.pf.initialization": "lh",
               "knob.oracle.w": "0.25", "knob.groundhog.bandwidth": "3",
               "knob.groundhog.aux_weight": "0.25",
               "knob.output.floor_lam": "0.5"})
    assert r.status_code == 303 and len(started) == 1
    s = started[0]
    assert s.particles == 2000 and s.jitter == 0.3
    assert s.extra["prior_ranges"] == {"r__FREE": [0.1, 80.0]}
    assert s.extra["initialization"] == "lh"
    assert [p["weight"] for p in s.extra["aux_pools"]] == [0.25]
    assert s.extra["analogue_aux"] == EA.shipped_aux_label()   # preset name kept
    assert s.extra["knobs"] == {
        "groundhog.aux_weight": 0.25, "groundhog.bandwidth": 3,
        "oracle.w": 0.25, "output.floor_lam": 0.5, "pf.initialization": "lh",
        "pf.jitter": 0.3, "pf.particles": 2000, "pf.prior.r": [0.1, 80.0]}
    assert runs_mod.is_modified(s) and runs_mod.is_contained(s)
    # each changed value by its label (particles has a row of its own)
    ms = dict(spec_settings(s))["model settings"]
    assert ms.startswith("Kernel jitter 0.3 (default 0.15), ")
    assert "Particle initialization Latin hypercube" in ms
    assert "Particles" not in ms
    assert dict(spec_settings(s))["files"] == "non-hub names (-modified)"
    # the record reads back as the effective table
    rows = {r["key"]: r for r in K.effective(json.loads(s.to_json()))}
    assert rows["pf.prior.r"]["value"] == (0.1, 80.0)
    assert rows["oracle.w"]["value"] == 0.25


def test_older_field_names_are_the_same_knobs(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    _post({"particles": "2000", "knob.pf.particles": "2000"})     # agree
    _post({"particles": "10000", "knob.pf.particles": "3000"})    # field untouched
    _post({"replicates": "5", "weeks_to_drop": "1",
           "season_start": "2097-10-01", "drop_same_day": "1"})
    assert [s.particles for s in started] == [2000, 3000, 10_000]
    s = started[2]
    assert (s.replicates, s.weeks_to_drop, s.season_start, s.drop_same_day) \
        == (5, 1, "2097-10-01", True)
    assert s.extra["knobs"] == {"pf.replicates": 5, "run.drop_same_day": True,
                                "run.season_start": "2097-10-01",
                                "run.weeks_to_drop": 1}
    # two different off-shipped values for one knob: refused, nothing runs
    _post({"particles": "2000", "knob.pf.particles": "3000"})
    assert len(started) == 3 and ui_state._status.get("running") is None
    assert "two values" in ui_state._status.get("flash", "")


@pytest.mark.parametrize("data,msg", [
    ({"knob.oracle.w": "2"}, "outside"),
    ({"knob.pf.jitter": "nan"}, "finite"),
    ({"knob.oracle.count_floor": "5"}, "coming later"),
    ({"knob.pf.particle": "5"}, "unknown knob"),
    ({"replicates": "0"}, "pf.replicates"),
    # typed as text: valid to the browser's number box, not a whole number
    ({"particles": "1e4"}, "pf.particles"),
    ({"replicates": "2.5"}, "pf.replicates"),
    ({"weeks_to_drop": "one"}, "run.weeks_to_drop"),
    ({"knob.oracle.w": "0.25", "submit_modified": "1"}, "needs a reason"),
    ({"members": "3", "knob.pf.prior.r": "0.1,80"}, "two-strain"),
    # a knob field repeated in one form: refused, never the last value
    ({"knob.oracle.w": ["0.25", "0.5"]}, "more than once"),
    ({"knob.oracle.w": ["0.25", "0.25"]}, "knob.oracle.w"),
    ({"knobs": "{not json"}, "not readable JSON"),
])
def test_a_refused_knob_starts_nothing(tmp_path, monkeypatch, data, msg,
                                       pf_engine_ready):
    started = _capture_run(monkeypatch, tmp_path)
    r = _post(data)
    assert r.status_code == 303
    assert started == [] and ui_state._status.get("running") is None
    assert msg in ui_state._status.get("flash", "")
    assert "Not run" in ui_state._status.get("flash", "")
    assert ui_state._status.get("flash_kind") == "warn"


@pytest.mark.parametrize("field,typed,key", [
    ("particles", "1e4", "pf.particles"),
    ("replicates", "2.5", "pf.replicates"),
    ("weeks_to_drop", "1e1", "run.weeks_to_drop")])
def test_a_number_the_browser_allows_is_refused_on_the_panel(
        tmp_path, monkeypatch, field, typed, key):
    """The browser's number box passes 1e4; an int field answered with a
    raw JSON 422 page. Now the panel's own refusal, the typed value kept."""
    started = _capture_run(monkeypatch, tmp_path)
    r = _post({field: typed})
    assert r.status_code == 303 and started == []
    assert (f"Not run: model settings: {key}: '{typed}' is not a valid int."
            in ui_state._status["flash"])
    page = client.get("/forecast").text
    assert '<details class="adv" open data-refused id="model-settings"' in page
    why = page.split('id="ms-refused">')[1].split("</div>")[0]
    assert f"{K.BY_KEY[key].label}: &#39;{typed}&#39; is not a valid int." in why
    assert f'name="{field}" id="ks-{key.replace(".", "-")}" value="{typed}"' in page


def test_a_replay_refuses_a_number_the_browser_allows_in_words(tmp_path,
                                                               monkeypatch,
                                                               pf_engine_ready):
    from app.core import retro as core_retro
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(core_retro, "available_seasons", lambda: ["2024-25"])
    monkeypatch.setattr(core_retro, "season_vintages",
                        lambda s: ["2024-11-02", "2024-11-09"])
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append((a, k)))
    ui_state._status["running"] = None
    r = client.post("/retro/run", data={
        "season": "2024-25", "locations": "panel6", "engine": "pf",
        "replicates": "3.5"}, follow_redirects=False)
    assert r.status_code == 303 and launched == []
    assert ("Not started: model settings: pf.replicates: '3.5' is not a "
            "valid int." in ui_state._status["flash"])


def test_a_number_typed_with_commas_is_read_and_a_blank_is_the_default(
        tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    _post({"particles": "20,000", "replicates": "", "weeks_to_drop": ""})
    assert len(started) == 1
    assert (started[0].particles, started[0].replicates,
            started[0].weeks_to_drop) == (20_000, 3, 0)


def test_a_knob_that_does_not_apply_is_ignored_and_not_recorded(tmp_path,
                                                                monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    _post({"engine": "analogue", "particles": "2000", "knob.oracle.w": "0.25",
           "replicates": "5"})
    _post({"engine": "pf", "knob.groundhog.bandwidth": "3"})
    _post({"oracle": "none", "knob.oracle.w": "0.25"})
    assert all("knobs" not in s.extra for s in started), \
        [s.extra for s in started]
    assert started[0].particles == 10_000 and started[0].replicates == 3


def test_the_override_is_recorded_with_its_reason(tmp_path, monkeypatch):
    started = _capture_run(monkeypatch, tmp_path)
    _post({"knob.oracle.w": "0.25", "submit_modified": "1",
           "modified_reason": "lead's call, week 42"})
    s = started[0]
    assert s.extra["knobs_override"] == "lead's call, week 42"
    assert K.hub_names(s) and not runs_mod.is_contained(s)
    # the settings say how the files were named; the reason is the run
    # page's (its Modified model settings card), never a settings row
    pairs = dict(spec_settings(s))
    assert pairs["files"] == "hub names, by override"
    assert "lead's call" not in " ".join(pairs.values())
    # ticked with nothing modified: nothing to override, nothing recorded
    _post({"submit_modified": "1", "modified_reason": "x"})
    assert "knobs_override" not in started[1].extra


def test_the_override_never_carries_over_to_the_next_run(tmp_path, monkeypatch):
    """M2: after a run exported under the hub names by override, the box
    stayed ticked and the reason filled, so the next run's new settings
    went out under the hub names with the old reason. The override is
    one run's decision: a queued run clears it from the form and it is
    never kept across a restart; a refusal keeps the typed reason for the
    retry."""
    from app.core import runs as _runs
    from app.ui import forecast_aids as FA
    monkeypatch.setattr(_runs, "APP_STATE", tmp_path)
    started = _capture_run(monkeypatch, tmp_path)
    # refused (a value out of range): the box and the reason stay
    _post({"knob.oracle.w": "2", "submit_modified": "1",
           "modified_reason": "Reason A"})
    assert started == []
    assert ui_state._last_form["submit_modified"] is True
    assert ui_state._last_form["modified_reason"] == "Reason A"
    # run A: queued with the override; the form after it starts unticked
    _post({"knob.oracle.w": "0.25", "submit_modified": "1",
           "modified_reason": "Reason A"})
    assert started[0].extra["knobs_override"] == "Reason A"
    assert ui_state._last_form["submit_modified"] is False
    assert ui_state._last_form["modified_reason"] == ""
    html = client.get("/forecast").text
    assert 'id="ms-ovr">' in html and 'id="ms-ovr" checked>' not in html
    assert 'id="ms-why" hidden' in html
    assert 'value="Reason A"' not in html
    # run B with other settings, posted as the page now stands: non-hub
    _post({"knob.groundhog.bandwidth": "4"})
    assert "knobs_override" not in started[1].extra
    assert not K.hub_names(started[1])
    # never written to app/state/last_form.json, nor read back from it
    FA.save_last_form({"locations": ["Ohio"], "submit_modified": True,
                       "modified_reason": "Reason A"})
    kept = json.loads((tmp_path / FA.LAST_FORM_NAME).read_text())
    assert "submit_modified" not in kept and "modified_reason" not in kept
    (tmp_path / FA.LAST_FORM_NAME).write_text(json.dumps(
        {"locations": ["Ohio"], "submit_modified": True,
         "modified_reason": "older file"}))
    assert FA.load_last_form() == {"locations": ["Ohio"]}


def test_the_settings_row_is_short_and_in_words(tmp_path, monkeypatch):
    """The Latest run card's "model settings" row was a 7-line paragraph:
    raw keys, the digest and the override's reason, repeating the
    particles and replicates rows above it. Now: the changed values by
    their labels, a number with its default, less the knobs with a row of
    their own; a short "files" row; the Oracle step row no longer says
    "console default" for a run that changed its weight."""
    s = RunSpec(engine="all", forecast_date=FD, locations=["Ohio"],
                particles=1000, replicates=1,
                extra=K.write_extra(
                    {"oracle.w": 0.25, "pf.seed_denominator": "season_total_early",
                     "pf.particles": 1000, "pf.replicates": 1},
                    ui_forecast._run_extra(2, "realtime"),
                    override="2026-10-12 decision; docs/team/submission.md"))
    pairs = dict(spec_settings(s))
    assert pairs["model settings"] == (
        "Seed denominator expected total (early season), "
        "Oracle blend weight 0.25 (default 0.5)")
    assert pairs["files"] == "hub names, by override"
    assert pairs["particles"] == "1,000" and pairs["replicates"] == "1"
    assert pairs["Oracle step"] == "on, weight 0.25"
    text = " ".join(pairs.values())
    assert "2026-10-12" not in text and "season_total_early" not in text
    assert K.digest(K.record_of(s)) not in text
    # only knobs with their own rows changed: named, not repeated
    s2 = RunSpec(engine="all", forecast_date=FD, locations=["Ohio"],
                 particles=1000, extra=K.write_extra(
                     {"pf.particles": 1000},
                     ui_forecast._run_extra(2, "realtime")))
    pairs = dict(spec_settings(s2))
    assert pairs["model settings"] == "Particles changed"
    assert pairs["files"] == "non-hub names (-modified)"
    assert pairs["Oracle step"] == "on (console default)"
    # another Oracle-step setting: plainly "on"
    s3 = RunSpec(engine="all", forecast_date=FD, locations=["Ohio"],
                 extra=K.write_extra({"oracle.w_aux": 0.25},
                                     ui_forecast._run_extra(2, "realtime")))
    assert dict(spec_settings(s3))["Oracle step"] == "on"


# --- the console run: files, records, containment ------------------------------------

def _knob_run(srv_, nd, override=""):
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=["Ohio", "Utah"],
                   extra=K.write_extra(nd, ui_forecast._run_extra(2, "vintage"),
                                       override=override))
    ui_pipeline._run_all(spec)
    row = Ledger().rows(1)[0]
    return (spec, row, json.loads(row["outcome"]),
            runs_mod.APP_STATE / "workroots" / row["run_id"])


def test_a_modified_run_exports_under_the_non_hub_names(console):
    srv_, raw = console
    spec, row, out, w = _knob_run(srv_, {"oracle.w": 0.25})
    assert set(out["submissions"]) == {"NAU_PyBNF-OracleSIHRS-modified",
                                       "NAU_PyBNF-GroundHogCGR-modified"}
    for mid, p in out["submissions"].items():
        p = Path(p)
        assert p.parent.name == mid and p.name == f"2098-01-11-{mid}.csv"
    assert not list((w / "submission").glob("NAU_PyBNF-OracleSIHRS/*"))
    assert out["archived"].startswith("skipped: modified model settings")
    rec = json.loads((w / "knobs.json").read_text())
    assert rec["values"] == {"oracle.w": 0.25} and rec["override"] is None
    assert rec["digest"] == K.digest({"oracle.w": 0.25})
    res = json.loads((w / "results.json").read_text())
    assert res["knobs"]["values"] == {"oracle.w": 0.25}
    # the step ran with the knob and says so
    prov = oracle_mod.read_provenance(w)
    assert prov["w"] == 0.25 and prov["specification"] == "modified"
    assert prov["knobs"] == {"oracle.w": 0.25}
    # marked on the ledger surfaces, kept off the shipped ones
    assert "modified settings" in ui_shared._outcome_chips(row["outcome"])
    assert ui_shared._pf_member_label(out) == "Oracle SIHRS (modified)"
    assert ui_shared._latest_results() == (None, None)
    # Output's report card asks for it by name and shows it badged
    assert ui_shared._latest_results(include_modified=True)[0] == row["run_id"]
    files = ui_output._submission_files(w)
    assert all(f["modified"] and not f["submittable"] for f in files)
    assert ui_shared._run_label(row["run_id"], row["spec"]).endswith(
        "· modified settings")


def test_the_override_writes_hub_names_archives_and_records_why(console):
    srv_, raw = console
    spec, row, out, w = _knob_run(srv_, {"oracle.w": 0.25},
                                  override="the lead asked for it")
    assert set(out["submissions"]) == {"NAU_PyBNF-OracleSIHRS",
                                       "NAU_PyBNF-GroundHogCGR"}
    assert out["archived"] == "archived"
    assert out["knobs"]["override"] == {"reason": "the lead asked for it"}
    rec = json.loads((w / "knobs.json").read_text())
    assert rec["override"] == {"reason": "the lead asked for it"}
    res = json.loads((w / "results.json").read_text())
    assert res["knobs"]["override"]["reason"] == "the lead asked for it"
    assert json.loads(res["spec"])["extra"]["knobs_override"] == \
        "the lead asked for it"
    assert ui_shared._latest_results()[0] == row["run_id"]   # back, badged
    assert "hub names by override" in ui_shared._outcome_chips(row["outcome"])


def test_the_floor_knob_reaches_every_floor(console, monkeypatch):
    import app.core.floor as floor_mod
    srv_, raw = console
    seen = []
    monkeypatch.setattr(floor_mod, "floor_samples",
                        lambda s, loc, d, recent=None, lam=None:
                        seen.append(("s", lam)) or s)
    monkeypatch.setattr(floor_mod, "floor_quantiles",
                        lambda q, lam=None: seen.append(("q", lam)) or q)
    _knob_run(srv_, {"output.floor_lam": 0.5})
    assert seen and all(lam == 0.5 for _, lam in seen)
    assert {k for k, _ in seen} == {"s", "q"}


# --- the Oracle step and the Groundhog read the record ------------------------------

def _per_seed(prov):
    return prov["quantiles"]["primary"]["per_seed"]


def test_oracle_step_knobs_equal_the_librarys_own_arguments(hubfiles, tmp_path):
    raw = _samples()
    m0, p0 = oracle_mod.apply_week(raw, ASOF, tmp_path / "a")
    m1, p1 = oracle_mod.apply_week(raw, ASOF, tmp_path / "b", extra={})
    assert m0 == m1                        # no knob: the shipped member exactly
    mw, pw = oracle_mod.apply_week(raw, ASOF, tmp_path / "c", w=0.25)
    mk, pk = oracle_mod.apply_week(raw, ASOF, tmp_path / "d",
                                   extra={"knobs": {"oracle.w": 0.25}})
    assert mk == mw and _per_seed(pk) == _per_seed(pw)
    assert mk != m0
    seed = K.BY_KEY["oracle.submitted_seed"].choices[2]
    ms, ps = oracle_mod.apply_week(raw, ASOF, tmp_path / "e",
                                   submitted_seed=seed)
    mks, pks = oracle_mod.apply_week(
        raw, ASOF, tmp_path / "f", extra={"knobs": {"oracle.submitted_seed": seed}})
    assert mks == ms and pks["submitted_seed"] == seed


def test_the_flusurv_share_knob_is_resolved_per_state(hubfiles, tmp_path):
    raw = _samples()
    _, p = oracle_mod.apply_week(raw, ASOF, tmp_path / "a",
                                 extra={"knobs": {"oracle.w_aux": 0.0}})
    mix = p["bank"]["mixture"]
    assert mix["w_aux_nominal"] == 0.0
    if mix["state"] == "both":
        assert mix["w_aux"] == 0.0
        assert all(e.get("n_flusurv_drawn", 0) == 0
                   for e in p["locations"].values())


def test_the_groundhog_window_knob_reaches_the_library(hubfiles, monkeypatch):
    import app.core.engines.analogue as an_engine
    monkeypatch.setattr(an_engine, "vintage_path", lambda d: hubfiles["vintage"])
    monkeypatch.setattr(an_engine, "LOCATIONS", hubfiles["locations"])
    calls = []
    real = an_engine.AN.forecast

    def spy(*a, **k):
        calls.append(k.get("bandwidth", "absent"))
        return real(*a, **k)
    monkeypatch.setattr(an_engine.AN, "forecast", spy)
    an_engine.run(RunSpec("analogue", ASOF, ["Ohio"]))
    assert calls and set(calls) == {"absent"}        # the shipped call
    calls.clear()
    an_engine.run(RunSpec("analogue", ASOF, ["Ohio"],
                          extra={"knobs": {"groundhog.bandwidth": 3}}))
    assert calls and set(calls) == {3}


# --- old rows ------------------------------------------------------------------------

def test_old_ledger_rows_are_never_marked_modified(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    old = RunSpec(engine="all", forecast_date=FD, replicates=1,
                  particles=2000, season_start="2097-10-01", jitter=0.3)
    oid = led.open_run(old, Path("pending"), {})
    led.close_run(oid, "ok", {})
    new = RunSpec(engine="all", forecast_date=FD,
                  extra=K.write_extra({"pf.particles": 2000}, {}))
    nid = led.open_run(new, Path("pending"), {})
    led.close_run(nid, "ok", {})
    for s in (old, old.to_json(), json.loads(old.to_json())):
        assert not runs_mod.is_modified(s)
        assert "model settings" not in dict(spec_settings(s))
    assert not runs_mod.is_contained(old)
    html = client.get("/runs").text
    orow = html.split(f'href="/runs/{oid}"', 1)[1].split("</tr>", 1)[0]
    nrow = html.split(f'href="/runs/{nid}"', 1)[1].split("</tr>", 1)[0]
    assert "modified settings" not in orow
    assert ('uk-badge--warn' in nrow
            and '<span class="uk-badge-t">modified settings</span>' in nrow)
    page = client.get(f"/runs/{nid}").text
    assert 'id="modified-note"' in page and "non-hub name" in page
    assert 'id="modified-note"' not in client.get(f"/runs/{oid}").text


def test_rerun_carries_the_knobs_but_never_the_override(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    led = Ledger()
    locs = ["Ohio", "US"]
    spec = RunSpec(engine="all", forecast_date=FD, locations=locs,
                   jitter=0.3,
                   extra=K.write_extra({"pf.jitter": 0.3, "oracle.w": 0.25},
                                       ui_forecast._run_extra(2, "realtime"),
                                       override="why"))
    rid = led.open_run(spec, Path("pending"), {})
    led.close_run(rid, "stopped", {})
    started = _capture_run(monkeypatch, tmp_path)
    r = client.post(f"/runs/{rid}/rerun", follow_redirects=False)
    assert r.status_code == 303 and len(started) == 1
    s = started[0]
    assert s.jitter == 0.3
    assert s.extra["knobs"] == {"oracle.w": 0.25, "pf.jitter": 0.3}
    assert "knobs_override" not in s.extra
    assert "non-hub name" in ui_state._status.get("flash", "")
    assert "never carried over" in ui_state._status.get("flash_detail", "")


# --- the retrospective ------------------------------------------------------------------

SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"


def _gh_season(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no particle filter here")
    monkeypatch.setattr(retro.pf_engine, "prepare", boom)
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    seen = []

    def fake_an(spec):
        seen.append(dict(spec.extra or {}))
        return {"Ohio": {h: {0.5: 5.0} for h in ("0", "1", "2", "3")}}
    monkeypatch.setattr(retro.an_engine, "run", fake_an)
    return seen


def test_run_season_records_the_knobs_and_refuses_a_different_resume(
        tmp_path, monkeypatch):
    seen = _gh_season(monkeypatch)
    root = tmp_path / SEASON
    nd = {"groundhog.bandwidth": 3}
    wx = K.retro_week_extra(EA.aux_preset(EA.SHIPPED_AUX), nd)
    assert wx.__name__.endswith(f"+knobs@{K.digest(nd)}")
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue",
                     week_extra=wx, settings={"knobs": nd})
    s = retro.read_meta(root)["settings"]
    assert s["knobs"] == nd and s["knobs_digest"] == K.digest(nd)
    assert seen and all(x["knobs"] == nd for x in seen)
    # in words, as a forecast run's settings are, then their digest (the
    # season page's badge says only that they changed)
    pairs = retro.settings_summary(retro.read_meta(root))
    assert ("model settings", K.words(nd)) in pairs
    assert pairs[pairs.index(("model settings", K.words(nd))) + 1] == (
        "settings digest", K.digest(nd))
    assert json.loads(retro.resume_form_fields(
        {"settings": {**s, "scope": "panel6"}})["knobs"]) == nd
    # the tree never wears the shipped names, and never publishes
    from app.core import report_season, site_build
    assert report_season.names_for_root(root)["analogue"].endswith(
        "(modified settings)")
    assert SEASON not in site_build.discover_seasons((("lab", tmp_path),))
    # resuming with other knobs (or none) would mix two configurations
    for other in ({}, {"groundhog.bandwidth": 4}):
        with pytest.raises(retro.KnobsMismatch):
            retro.run_season(root, SEASON, ["Ohio"], width=1,
                             engine="analogue", settings={"knobs": other})
    assert retro.read_meta(root)["settings"]["knobs"] == nd    # untouched
    # the same knobs resume
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue",
                     week_extra=wx, settings={"knobs": nd})


def test_a_tree_from_before_the_registry_resumes_unmarked(tmp_path, monkeypatch):
    _gh_season(monkeypatch)
    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue",
                     particles=2000)
    meta = retro.read_meta(root)
    meta["settings"].pop("knobs", None)                 # as an old record
    meta["settings"].pop("knobs_digest", None)
    retro.write_meta(root, meta)
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue",
                     particles=2000, settings={"knobs": {"pf.particles": 2000}})
    assert "knobs" not in retro.read_meta(root)["settings"]
    with pytest.raises(retro.KnobsMismatch):
        retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue")


def test_the_retro_route_refuses_a_resume_with_other_knobs(tmp_path, monkeypatch,
                                                           pf_engine_ready):
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg", lambda *a, **k: launched.append((a, k)))
    root = tmp_path / SEASON
    (root / "weeks" / W1).mkdir(parents=True)
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "knobs": {"oracle.w": 0.25}}})
    monkeypatch.setattr(ui_retro_seasons, "_weeks_done", lambda p: 1)
    base = {"season": SEASON, "locations": "panel6", "engine": "pf",
            "mode": "resume", "national": "0"}
    client.post("/retro/run", data={**base, "knob.oracle.w": "0.3"},
                follow_redirects=False)
    assert launched == []
    assert "other model settings" in ui_state._status.get("flash", "")
    assert "mix two configurations" in ui_state._status.get("flash_detail", "")
    # out of the retro scope, out of range, or one knob sent twice: refused
    # before anything moves
    for bad in ({"knob.run.weeks_to_drop": "1"}, {"particles": "500"},
                {"knob.oracle.w": ["0.25", "0.3"]}):
        ui_retro_seasons._retro_status.pop(SEASON, None)
        client.post("/retro/run", data={**base, **bad}, follow_redirects=False)
        assert launched == [] and "Not started" in ui_state._status["flash"]
        assert ui_state._status.get("flash_kind") == "warn"
    # the recorded knobs (the one-click resume's JSON field) launch
    ui_retro_seasons._retro_status.pop(SEASON, None)
    client.post("/retro/run", data={**base, "knobs": '{"oracle.w": 0.25}'},
                follow_redirects=False)
    assert len(launched) == 1
    args, kw = launched[0]
    assert args[5]["knobs"] == {"oracle.w": 0.25}
    assert kw["week_extra"].__name__.endswith(
        "+knobs@" + K.digest({"oracle.w": 0.25}))
    assert kw["week_extra"](W1, 0, [W1])["knobs"] == {"oracle.w": 0.25}


def test_fit_manifest_leaves_post_fit_knobs_out():
    extra = K.write_extra({"oracle.w": 0.25, "pf.jitter": 0.3}, {}, retro=True)
    fit = K.fit_extra(extra)
    assert fit["knobs"] == {"pf.jitter": 0.3} and fit["jitter"] == 0.3
    assert "knobs" not in K.fit_extra(K.write_extra({"oracle.w": 0.25}, {}))


def test_the_retro_route_refuses_a_resume_over_other_locations(
        tmp_path, monkeypatch, pf_engine_ready):
    """Completed weeks are skipped on resume, so another location scope (or
    the national row switched) would pool weeks fitted over different
    lists; the recorded list resumes."""
    monkeypatch.setattr(ui_retro_seasons, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(ui_retro_seasons, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append((a, k)))
    root = tmp_path / SEASON
    (root / "weeks" / W1).mkdir(parents=True)
    six = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
           "California"]
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "scope": "panel6",
                                         "locations": six}})
    monkeypatch.setattr(ui_retro_seasons, "_weeks_done", lambda p: 1)
    base = {"season": SEASON, "engine": "pf", "mode": "resume"}
    for other in ({"locations": "all", "national": "0"},
                  {"locations": "panel6", "national": "1"}):
        ui_retro_seasons._retro_status.pop(SEASON, None)
        client.post("/retro/run", data={**base, **other},
                    follow_redirects=False)
        assert launched == [], other
        assert "mix two location scopes" in ui_state._status.get(
            "flash_detail", "")
    ui_retro_seasons._retro_status.pop(SEASON, None)
    client.post("/retro/run", data={**base, "locations": "panel6",
                                    "national": "0"}, follow_redirects=False)
    assert len(launched) == 1


def test_run_season_refuses_a_resume_over_other_locations(tmp_path,
                                                          monkeypatch):
    """The location rule lives in retro.run_season, so the CLI (and any
    other caller) refuses it like the console; the recorded list, with
    the national row spelled either way, resumes."""
    _gh_season(monkeypatch)
    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio", "US"], width=1,
                     engine="analogue")
    for other in (["Ohio"], ["Ohio", "Texas", "US"]):
        with pytest.raises(retro.LocationsMismatch,
                           match="mix two location scopes"):
            retro.run_season(root, SEASON, other, width=1,
                             engine="analogue")
    assert retro.read_meta(root)["settings"]["locations"] == ["Ohio", "US"]
    retro.run_season(root, SEASON, ["US", "Ohio"], width=1,
                     engine="analogue")


def test_cli_retro_reports_a_location_refusal(monkeypatch, tmp_path):
    from flubnf.cli import app
    _cli_locations(monkeypatch, tmp_path)

    def refuse(*a, **k):
        raise retro.LocationsMismatch("mix two location scopes")
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    monkeypatch.setattr(retro, "run_season", refuse)
    r = CliRunner().invoke(app, ["retro", SEASON, "--locations", "Ohio",
                                 "--root", str(tmp_path / SEASON)])
    assert r.exit_code == 2 and "refused" in r.output
    assert "location scopes" in r.output


def _cli_locations(monkeypatch, tmp_path):
    import flubnf.settings as fs
    loc = tmp_path / "locations.csv"
    loc.write_text("location,abbreviation,location_name,population\n"
                   "39,OH,Ohio,1\nUS,US,US,1\n")
    monkeypatch.setattr(fs, "LOCATIONS", loc)


def test_cli_retro_takes_knobs(monkeypatch, tmp_path):
    from flubnf.cli import app
    _cli_locations(monkeypatch, tmp_path)
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    got = []
    monkeypatch.setattr(retro, "run_season",
                        lambda *a, **k: got.append((a, k)) or [])
    r = CliRunner().invoke(app, [
        "retro", SEASON, "--locations", "Ohio", "--width", "1",
        "--root", str(tmp_path / SEASON),
        "--knob", "oracle.w=0.25", "--knob", "pf.particles=2000"])
    assert r.exit_code == 0, r.output
    (a, k), = got
    assert k["particles"] == 2000
    assert k["settings"]["knobs"] == {"oracle.w": 0.25, "pf.particles": 2000}
    assert k["week_extra"].__name__.endswith(
        "+knobs@" + K.digest({"oracle.w": 0.25}))
    assert k["week_extra"](W1, 0, [W1])["knobs"] == {"oracle.w": 0.25}
    # refused: out of range, out of the retro scope, malformed
    for bad in ("oracle.w=2", "output.floor_lam=0.5", "oracle.w"):
        r = CliRunner().invoke(app, ["retro", SEASON, "--locations", "Ohio",
                                     "--knob", bad])
        assert r.exit_code != 0, bad
    # no knob: the shipped call (no settings, no drop_same_day keyword)
    got.clear()
    CliRunner().invoke(app, ["retro", SEASON, "--locations", "Ohio",
                             "--root", str(tmp_path / SEASON)])
    assert "settings" not in got[0][1]


def test_the_season_page_wears_the_modified_badge():
    t = srv.templates.env.get_template("retro_season.html")
    ctx = {"active": "Retrospective", "season": SEASON,
           "model_name": lambda m: m, "archive": "",
           "preparing": {"phase": "scoring", "elapsed_s": 1.0}}
    html = t.render(**ctx, knobs_modified=True)
    # a badge (icon and word) that says it alone: the settings row names
    # each change and the digest
    assert '<span class="uk-badge uk-badge--warn" id="rs-knobs"' in html
    assert "modified settings</span>" in html
    assert 'id="tip-rs-knobs"' not in html
    assert "modified settings</span>" not in t.render(**ctx,
                                                       knobs_modified=False)


def test_cli_retro_reports_a_digest_refusal(monkeypatch, tmp_path):
    from flubnf.cli import app

    _cli_locations(monkeypatch, tmp_path)

    def refuse(*a, **k):
        raise retro.KnobsMismatch("mixed")
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    monkeypatch.setattr(retro, "run_season", refuse)
    r = CliRunner().invoke(app, ["retro", SEASON, "--locations", "Ohio",
                                 "--root", str(tmp_path / SEASON),
                                 "--knob", "oracle.w=0.25"])
    assert r.exit_code == 2 and "refused" in r.output


def test_cli_retro_refuses_a_bad_or_empty_season_and_roots_in_app_state(
        monkeypatch, tmp_path):
    """A malformed season is a usage error (never a traceback); a season
    the archive holds no vintage for is refused (never a '0 weeks complete'
    record); the default root is the console's, whatever the shell's cwd."""
    from flubnf.cli import app
    from app.core import runs as runs_mod
    _cli_locations(monkeypatch, tmp_path)
    got = []
    monkeypatch.setattr(retro, "run_season",
                        lambda *a, **k: got.append((a, k)) or [])
    for bad in ("not-a-season", "2024-26", "2024"):
        r = CliRunner().invoke(app, ["retro", bad, "--locations", "Ohio"])
        assert r.exit_code == 2, (bad, r.output)
        assert "is not a season" in r.output, bad
    monkeypatch.setattr(retro, "season_vintages", lambda s: [])
    r = CliRunner().invoke(app, ["retro", "1999-00", "--locations", "Ohio"])
    assert r.exit_code == 2 and "no archived vintages" in r.output
    assert not got
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    monkeypatch.chdir(tmp_path)
    r = CliRunner().invoke(app, ["retro", SEASON, "--locations", "Ohio",
                                 "--width", "1"])
    assert r.exit_code == 0, r.output
    assert got[0][0][0] == (runs_mod.APP_STATE / "retro" / SEASON).resolve()


def test_a_missing_data_rule_records_every_flagged_week(console, monkeypatch):
    """data.trailing_zero / data.partial_week (app/core/missing.py): each
    member's flagged weeks go into the run's outcome and its results line;
    a shipped run carries no such key (the other tests hold that)."""
    import app.core.engines.analogue as an_engine
    import app.core.engines.pf as pf_engine
    srv_, raw = console
    row = {"week": ASOF, "rule": "trailing zero", "value": 0.0}

    def fake_prepare(spec, w):
        Path(w).mkdir(parents=True, exist_ok=True)
        cells = [{"key": "Ohio_r0", "location": "Ohio", "replicate": 0,
                  "weeks_dropped": 1, "data_flags": [row]}]
        (Path(w) / "cells.json").write_text(json.dumps(cells))
        return cells

    real_run = an_engine.run

    def fake_an(spec, flags=None):
        flags.append({"location": "Ohio", **row})
        return real_run(spec)
    monkeypatch.setattr(pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(an_engine, "run", fake_an)
    spec, ledger_row, out, w = _knob_run(srv_, {"data.trailing_zero": "missing"})
    want = [{"location": "Ohio", **row}]
    assert out["data_flags"] == {"analogue": want, "pf": want}
    html = runs_mod.results_html(out, spec.to_json())
    assert (f"1 week to {ASOF} treated as unreported (trailing zero): "
            "Ohio 1") in html


def test_the_narrowing_knob_scales_the_member_about_its_medians(hubfiles, tmp_path):
    """oracle.narrow = k scales the submitted seed's samples about each
    horizon's median after the step: the medians hold, every band shrinks
    (a value ten times the median becomes 10^k times it), the recorded
    primary quantiles follow, the unnarrowed ones stay in the record, and
    k = 1 is the shipped member bitwise."""
    raw = _samples()
    m0, p0 = oracle_mod.apply_week(raw, ASOF, tmp_path / "a")
    m1, p1 = oracle_mod.apply_week(raw, ASOF, tmp_path / "b",
                                   extra={"knobs": {"oracle.narrow": 1.0}})
    assert m1 == m0 and not p1["narrowing"]["applied"]
    assert "unnarrowed" not in p1["quantiles"]["primary"]
    mk, pk = oracle_mod.apply_week(raw, ASOF, tmp_path / "c",
                                   extra={"knobs": {"oracle.narrow": 0.7}})
    assert pk["narrowing"] == {**pk["narrowing"], "k": 0.7, "applied": True}
    assert pk["specification"] == "modified" and pk["knobs"]["oracle.narrow"] == 0.7
    seed = str(pk["submitted_seed"])
    checked = 0
    for loc in m0:
        if loc not in pk["locations"] or pk["locations"][loc].get("state") == "outside":
            continue
        assert mk[loc]["origin"] == m0[loc]["origin"]          # the data block stays
        for h in ("0", "1", "2", "3"):
            x0 = np.asarray(m0[loc][h], float); xk = np.asarray(mk[loc][h], float)
            f = np.isfinite(x0)
            assert np.array_equal(np.isfinite(xk), f)
            med = float(np.median(x0[f]))
            if not med > 0:
                # the fixture has no zeros or NaN; the next test reaches this path
                assert np.array_equal(xk[f], x0[f])              # nothing to scale about
                continue
            assert np.allclose(np.median(xk[f]), med, rtol=1e-6)   # even counts interpolate
            above = f & (x0 > med)
            assert np.allclose(xk[above], med * (x0[above] / med) ** 0.7)
            assert np.all(xk[above] <= x0[above])
            # the recorded quantiles are the narrowed ones, the raw ones kept
            qk = pk["quantiles"]["primary"]["per_seed"][seed][loc][h]["unrounded"]
            q0 = p0["quantiles"]["primary"]["per_seed"][seed][loc][h]["unrounded"]
            qr = pk["quantiles"]["primary"]["unnarrowed"]["per_seed"][seed][loc][h]["unrounded"]
            if qk is None or q0 is None:
                continue
            # the record is the quantile map of the raw record; the member's own
            # quantiles agree to interpolation precision (narrow's docstring)
            assert np.allclose(oracle_mod.OR.finite_quantiles(xk), qk, rtol=1e-4)
            assert qr == q0
            assert qk[11] == pytest.approx(q0[11])
            assert qk[22] == pytest.approx(q0[11] * (q0[22] / q0[11]) ** 0.7)
            checked += 1
    assert checked > 0
    # the other blocks and the seed mean follow the recorded rule
    for key in ("secondary", "admissions_only", "null"):
        assert pk["quantiles"][key] == p0["quantiles"][key], key
    assert pk["quantiles"]["primary"]["unnarrowed"]["seed_mean"] == p0["quantiles"]["primary"]["seed_mean"]
    assert pk["quantiles"]["primary"]["seed_mean"] != p0["quantiles"]["primary"]["seed_mean"]
    assert pk["quantiles"]["primary"]["narrowed"] == 0.7
    # the knob label names it and the step bounds it, by the record and by the keyword
    assert "oracle.narrow=0.7" in K.label({"oracle.narrow": 0.7})
    for bad in (-0.5, 0.0, 1.5, float("nan")):
        with pytest.raises(ValueError, match="oracle.narrow"):
            oracle_mod.apply_week(raw, ASOF, tmp_path / "d", extra={"knobs": {"oracle.narrow": bad}})
    with pytest.raises(ValueError):
        oracle_mod.apply_week(raw, ASOF, tmp_path / "d2", narrow_k=1.5)


def test_the_narrowing_knob_narrows_the_identity_cells_too(hubfiles, tmp_path):
    """An identity cell ships the filter's own samples and the knob narrows
    them like every other cell's (the 6b screen narrowed the stored
    record's every cell); the null record stays, so the narrowed primary
    record differs from it and the unnarrowed one still equals it."""
    raw = _samples(); raw["Utah"][hz.ORIGIN] = [0.0] * 400      # m_0 = 0: not eligible
    m0, p0 = oracle_mod.apply_week(raw, ASOF, tmp_path / "a")
    mk, pk = oracle_mod.apply_week(raw, ASOF, tmp_path / "b",
                                   extra={"knobs": {"oracle.narrow": 0.7}})
    seed = str(pk["submitted_seed"])
    e = pk["locations"]["Utah"]
    assert e["state"] == "not eligible" and not e["active"]
    assert mk["Utah"]["origin"] == m0["Utah"]["origin"] and mk["Utah"]["0"] != m0["Utah"]["0"]
    assert pk["quantiles"]["null"]["Utah"] == p0["quantiles"]["null"]["Utah"]
    assert pk["quantiles"]["primary"]["unnarrowed"]["per_seed"][seed]["Utah"] == p0["quantiles"]["null"]["Utah"]
    assert pk["quantiles"]["primary"]["per_seed"][seed]["Utah"] != p0["quantiles"]["null"]["Utah"]


def test_narrowing_keeps_non_finite_entries_and_a_zero_median_block_through_the_step(hubfiles, tmp_path):
    raw = _samples()
    raw["Ohio"]["2"][5] = float("nan")
    raw["Utah"]["1"] = [0.0] * 300 + raw["Utah"]["1"][300:]      # median 0: the cell is not eligible
    mk, pk = oracle_mod.apply_week(raw, ASOF, tmp_path / "k", extra={"knobs": {"oracle.narrow": 0.7}})
    m0, p0 = oracle_mod.apply_week(raw, ASOF, tmp_path / "o")
    x = np.asarray(mk["Ohio"]["2"], float)
    assert np.isnan(x).sum() == 1 and np.isnan(x[5])
    assert len(pk["quantiles"]["primary"]["per_seed"][str(pk["submitted_seed"])]["Ohio"]["2"]["unrounded"]) == 23
    assert mk["Utah"]["1"] == m0["Utah"]["1"]                    # nothing to scale about
    assert np.asarray(mk["Utah"]["3"]).max() < np.asarray(m0["Utah"]["3"]).max()   # identity cells are narrowed


def test_the_narrowing_knob_narrows_the_hub_rows_end_to_end(console):
    srv_, raw = console
    _, _, out0, w0 = _knob_run(srv_, {})
    _, rowk, outk, wk = _knob_run(srv_, {"oracle.narrow": 0.7})
    assert set(outk["submissions"]) == {"NAU_PyBNF-OracleSIHRS-modified", "NAU_PyBNF-GroundHogCGR-modified"}
    assert outk["knobs"]["label"].startswith("modified: oracle.narrow=0.7 (")
    prov = oracle_mod.read_provenance(wk)
    assert prov["narrowing"]["k"] == 0.7 and prov["narrowing"]["applied"]

    def table(out, mid):
        with open(out["submissions"][mid], newline="") as fh:
            return {(r["location"], r["horizon"], r["output_type_id"]): float(r["value"])
                    for r in csv.DictReader(fh)}
    t0 = table(out0, "NAU_PyBNF-OracleSIHRS"); tk = table(outk, "NAU_PyBNF-OracleSIHRS-modified")
    assert set(t0) == set(tk)
    for loc in ("39", "49"):
        for h in "0123":
            assert tk[(loc, h, "0.5")] == pytest.approx(t0[(loc, h, "0.5")], abs=1)
            assert tk[(loc, h, "0.975")] < t0[(loc, h, "0.975")]
            assert tk[(loc, h, "0.025")] > t0[(loc, h, "0.025")]
    # the Groundhog file is byte-identical: the knob touches one member
    assert Path(out0["submissions"]["NAU_PyBNF-GroundHogCGR"]).read_bytes() == \
        Path(outk["submissions"]["NAU_PyBNF-GroundHogCGR-modified"]).read_bytes()
