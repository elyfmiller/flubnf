"""The outlook model toggle: one map, every available model.

The v3 bundle carries hover cards for EACH model (pf and analogue; older
bundles also "ensemble"), all from the one quantile-CDF path
(categorical_probs_from_quantiles; PF samples reduced to the grid first).
Home and the weekly report render the default (PF) map plus, with two or
more models, an aria-pressed toggle that swaps fills, hovers and label
client-side.

Legacy runs (no bundle, or pre-v3) get the same toggle approximately when
results.json stores grids for two or more models, captioned "approximate,
from stored quantiles"; with one usable model they keep their exact
single-model cards and no control.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

import app.core.runs as runs_mod                    # noqa: E402
import app.ui.server as srv                         # noqa: E402
from app.ui import pipeline as ui_pipeline          # noqa: E402
from app.ui import shared as ui_shared              # noqa: E402
from app.core import horizons as hz                 # noqa: E402
from app.core import report_v2                      # noqa: E402

client = TestClient(srv.app)

OLD_MTIME = (1_000_000_000, 1_000_000_000)          # 2001: always stale


def _synth_run_all_models(workroot: Path):
    """Drive the real build path with synthetic PF samples and analogue
    quantiles for Ohio and US. `ens_q` (a quantile mean of the two) is for
    the legacy cases only and never reaches the build path."""
    from app.core import ensemble as ens
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="all", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(7)
    # canonical horizons: "0" is the FIRST forecast week; the shift grows
    # with weeks ahead (h+1 weeks past the anchor)
    pf_samples = {loc: {h: (rng.gamma(5.0, 20.0, 400)
                            + 10 * (int(h) + 1)).tolist()
                        for h in hz.HORIZONS}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    pf_q = {loc: ens.member_quantiles_from_samples(s)
            for loc, s in pf_samples.items()}
    # a deliberately different analogue: shifted samples, distinct grids
    an_q = {loc: ens.member_quantiles_from_samples(
                {h: (np.asarray(s[h]) * 0.7 + 25).tolist() for h in s})
            for loc, s in pf_samples.items()}
    ens_q = {loc: {h: {l: 0.5 * (pf_q[loc][h][l] + an_q[loc][h][l])
                       for l in pf_q[loc][h]}
                   for h in pf_q[loc]}
             for loc in pf_samples}
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    outcome = {}
    ui_pipeline._write_weekly_report(spec, workroot, pf_samples, obs,
                                     pd.DataFrame(), locs, n2f, 42.0, outcome,
                                     an_q=an_q)
    def cut(qd):
        return {loc: {h: {str(l): v for l, v in q.items()
                          if str(l) in ("0.1", "0.25", "0.5", "0.75", "0.9")}
                      for h, q in qs.items()} for loc, qs in qd.items()}
    (workroot / "results.json").write_text(json.dumps({
        "forecast_date": "2098-01-03", "observed": obs,
        "models": {"pf": cut(pf_q), "analogue": cut(an_q)}}))
    return {"pf_samples": pf_samples, "an_q": an_q, "ens_q": ens_q,
            "pf_q": pf_q, "obs": obs, "outcome": outcome}


# ---------------------------------------------------- the v3 bundle itself

def test_bundle_v3_carries_every_model_via_the_one_quantile_cdf_path(
        tmp_path):
    from app.core.report import categorical_probs_from_quantiles
    parts = _synth_run_all_models(tmp_path)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["version"] == report_v2.BUNDLE_VERSION
    # the v4 additive scope record: which states this run covered
    assert bundle["fitted_fips"] == ["39"]
    assert bundle["cards_model"] == "pf"            # the PF colours the map
    cbm = bundle["cards_by_model"]
    assert set(cbm) == {"pf", "analogue"}
    # every model's Ohio card equals the quantile-CDF computation on its own
    # grid (the pf card included)
    lo = parts["obs"]["Ohio"][-1][1]
    from flubnf.settings import load_locations
    locs = load_locations()
    pop = int(dict(zip(locs.location_name,
                       locs.population.astype(float)))["Ohio"])
    for model, q in (("pf", parts["pf_q"]), ("analogue", parts["an_q"])):
        # the card is the 1-week-ahead outlook: the first canonical horizon
        expect = categorical_probs_from_quantiles(
            q["Ohio"][hz.HORIZONS[0]], lo, pop, 0)
        got = cbm[model]["OH"]["probs"]
        for c in expect:
            assert abs(got[c] - expect[c]) < 1e-9, (model, c)
        assert cbm[model]["OH"]["fips"] == "39"
    # the models disagree (the toggle switches real computations)
    assert cbm["analogue"]["OH"]["probs"] != cbm["pf"]["OH"]["probs"]
    # per-model national cards ride along; the primary stays back-compat
    assert set(bundle["national_map_cards"]) == {"pf", "analogue"}
    assert bundle["national_map_card"] == \
        bundle["national_map_cards"]["pf"]
    # legacy fields unchanged for older readers
    assert "OH" in bundle["cards"] and bundle["details"]


# ------------------------------------------------------- the weekly report

def test_report_renders_the_toggle_with_every_bundled_model(tmp_path):
    _synth_run_all_models(tmp_path)
    html = (tmp_path / "report.html").read_text()
    # the compact aria-pressed toggle, above the map, default PF
    assert 'id="outlook-model"' in html
    assert html.index('id="outlook-model"') < html.index('id="map-anchor"')
    assert ('data-mmodel="pf" aria-pressed="true"') in html
    assert ('data-mmodel="analogue" aria-pressed="false"') in html
    assert 'data-mmodel="ensemble"' not in html
    for label in ("Oracle SIHRS categorical forecast", "Groundhog categorical forecast"):
        assert label in html, label
    # the label element the swap script retargets (one remains, above the map)
    assert html.count("data-mapmodel-label") >= 1
    # the swap payload and mechanics: per-state fills by fips, the
    # national group, and the honest click affordance
    assert "path[data-fips]" in html and 'data-fips="39"' in html
    assert "g.nat" in html
    assert "aria-pressed', String(on)" in html


def test_pf_only_run_gets_no_toggle_and_an_honest_label(tmp_path):
    """One available model: no toggle, PF label."""
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(3)
    pf_samples = {loc: {h: (rng.gamma(5.0, 20.0, 300)
                            + 8 * (int(h) + 1)).tolist()
                        for h in hz.HORIZONS}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    ui_pipeline._write_weekly_report(spec, tmp_path, pf_samples, obs,
                                     pd.DataFrame(), locs, n2f, 42.0, {})
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["cards_model"] == "pf"
    assert set(bundle["cards_by_model"]) == {"pf"}
    html = (tmp_path / "report.html").read_text()
    assert 'id="outlook-model"' not in html
    assert "data-mmodel=" not in html
    assert "Oracle SIHRS categorical forecast" in html


def test_v2_bundle_rebuilds_with_no_toggle_and_the_stored_label(
        tmp_path, monkeypatch):
    """A pre-per-model-cards (v2) bundle rebuilds as before: one model, no
    toggle, honest label."""
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    d = tmp_path / "archive" / "2098-01-03"
    _synth_run_all_models(d)
    b = d / report_v2.BUNDLE_NAME
    bundle = json.loads(b.read_text())
    bundle["version"] = 2
    bundle.pop("cards_by_model", None)
    bundle.pop("national_map_cards", None)
    b.write_text(json.dumps(bundle))
    (d / "report.html").write_text("<html><body>OLD FACE</body></html>")
    os.utime(d / "report.html", OLD_MTIME)
    srv._REPORT_REBUILD_FAILED.clear()
    r = client.get("/output/report?date=2098-01-03")
    assert r.status_code == 200 and "OLD FACE" not in r.text
    assert 'id="outlook-model"' not in r.text
    assert "data-mmodel=" not in r.text
    assert "Oracle SIHRS categorical forecast" in r.text                 # the label stays honest


# ------------------------------------------------------------- the home map

def _latest(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    parts = _synth_run_all_models(w)
    ui_shared._invalidate_scans()
    return w, parts


def test_home_outlook_gets_the_same_toggle(tmp_path, monkeypatch):
    w, _ = _latest(tmp_path, monkeypatch)
    by_model = srv._outlook_models(w.name)
    assert set(by_model) == {"pf", "analogue"}
    assert "39" in by_model["analogue"]              # fips-keyed, with data
    home = client.get("/").text
    assert 'id="outlook-model"' in home
    assert 'data-mmodel="pf" aria-pressed="true"' in home
    assert 'data-mmodel="analogue" aria-pressed="false"' in home
    # the toggle sits above the rendered map
    assert home.index('id="outlook-model"') < home.index('id="usmap"')
    # the label span is the relabel target and defaults to the PF
    assert 'data-mapmodel-label>Oracle SIHRS categorical forecast' in home
    assert "Groundhog categorical forecast" in home


def test_home_shows_no_toggle_for_a_single_model_pre_v3_bundle(
        tmp_path, monkeypatch):
    """A pre-v3 bundle whose results.json stores ONE model (the blend alone)
    cannot fund the toggle: exact single-model cards, no control, no
    approximation marker."""
    w, parts = _latest(tmp_path, monkeypatch)
    (w / "results.json").write_text(json.dumps({
        "forecast_date": "2098-01-03", "observed": parts["obs"],
        "models": {"ensemble": {loc: {h: {str(l): v for l, v in q.items()
                                          if str(l) in LV}
                                      for h, q in qd.items()}
                                for loc, qd in parts["ens_q"].items()}}}))
    b = w / report_v2.BUNDLE_NAME
    bundle = json.loads(b.read_text())
    bundle["version"] = 2
    bundle.pop("cards_by_model", None)
    bundle.pop("national_map_cards", None)
    b.write_text(json.dumps(bundle))
    ui_shared._invalidate_scans()
    assert srv._outlook_models(w.name) == {}
    home = client.get("/").text
    assert 'id="outlook-model"' not in home
    assert "data-mmodel=" not in home
    # the map and its honest one-model label render exactly as before
    assert 'id="usmap"' in home
    assert "Oracle SIHRS categorical forecast" in home
    assert "approximate, from stored quantiles" not in home


# ------------------------- the approximate toggle for stored legacy runs

LV = ("0.1", "0.25", "0.5", "0.75", "0.9")


def _results_with_all_models(workroot: Path, parts: dict) -> None:
    """Rewrite results.json as a legacy run stored it: pf, analogue AND
    ensemble at the five coarse levels."""
    def cut(qd):
        return {loc: {h: {str(l): v for l, v in q.items() if str(l) in LV}
                      for h, q in qs.items()} for loc, qs in qd.items()}
    (workroot / "results.json").write_text(json.dumps({
        "forecast_date": "2098-01-03", "observed": parts["obs"],
        "models": {"pf": cut(parts["pf_q"]),
                   "analogue": cut(parts["an_q"]),
                   "ensemble": cut(parts["ens_q"])}}))


def test_stored_pre_bundle_run_gets_the_approximate_toggle(
        tmp_path, monkeypatch):
    """A legacy run (results.json only): all card sets come from the stored
    grids via the quantile-CDF path, the toggle works and is captioned
    approximate, and the swap payload equals the server-rendered fills."""
    import re

    from app.core import usmap
    from app.core.report import categorical_probs_from_quantiles
    from flubnf.settings import load_locations
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    parts = _synth_run_all_models(w)
    (w / report_v2.BUNDLE_NAME).unlink()            # a pre-bundle run
    _results_with_all_models(w, parts)
    ui_shared._invalidate_scans()
    rid, res = ui_shared._latest_results()
    cards, meta = srv._outlook_cards(res, rid)
    # the PF is the default and the two shipped models are offered; the
    # stored blend is never a choice beside them (it renders only when a run
    # stored nothing else, see the single-model test above)
    assert meta["approx"] is True and meta["model"] == "pf"
    bm = meta["by_model"]
    assert set(bm) == {"pf", "analogue"}
    # each card is the exact CDF reading of its own five-level grid
    locs = load_locations()
    pop = int(dict(zip(locs.location_name,
                       locs.population.astype(float)))["Ohio"])
    lo = parts["obs"]["Ohio"][-1][1]
    for model, q in (("pf", parts["pf_q"]), ("analogue", parts["an_q"])):
        grid = {str(l): v for l, v in q["Ohio"][hz.HORIZONS[0]].items()
                if str(l) in LV}
        expect = categorical_probs_from_quantiles(grid, lo, pop, 0)
        got = bm[model]["39"]["probs"]
        for c in expect:
            assert abs(got[c] - expect[c]) < 1e-9, (model, c)
    home = client.get("/").text
    # the working toggle, default PF, no blend button
    assert 'id="outlook-model"' in home
    assert 'data-mmodel="pf" aria-pressed="true"' in home
    assert 'data-mmodel="analogue" aria-pressed="false"' in home
    assert 'data-mmodel="ensemble"' not in home
    # the approximation marker rides the caption
    assert "approximate, from stored quantiles" in home
    assert 'data-mapmodel-label>Oracle SIHRS categorical forecast' in home
    # the payload for the default model equals the rendered map exactly
    pay = usmap.state_swap_payload(bm["pf"])
    m = re.search(r'<path d="[^"]*" fill="([^"]+)" fill-opacity="([^"]+)"'
                  r'[^>]*data-fips="39"', home)
    assert m, "Ohio path missing from the home map"
    assert m.group(1) == pay["39"]["f"]
    assert float(m.group(2)) == pay["39"]["o"]


def test_pre_v3_bundle_with_multi_model_results_gets_the_toggle(
        tmp_path, monkeypatch):
    """A v2 bundle with multi-model results.json gets the approximate toggle."""
    w, parts = _latest(tmp_path, monkeypatch)
    b = w / report_v2.BUNDLE_NAME
    bundle = json.loads(b.read_text())
    bundle["version"] = 2
    bundle.pop("cards_by_model", None)
    bundle.pop("national_map_cards", None)
    b.write_text(json.dumps(bundle))
    _results_with_all_models(w, parts)
    ui_shared._invalidate_scans()
    home = client.get("/").text
    assert 'id="outlook-model"' in home
    assert 'data-mmodel="analogue"' in home
    assert "approximate, from stored quantiles" in home


def test_swap_payload_matches_the_server_render(tmp_path, monkeypatch):
    """The swap payload for the default model equals the server-rendered
    fills."""
    import re
    from app.core import usmap
    w, _ = _latest(tmp_path, monkeypatch)
    by_model = srv._outlook_models(w.name)
    # same scope as the server render (Ohio only), or the toggle would tell a
    # different story about card-less states
    pay = usmap.state_swap_payload(by_model["pf"], scope_fips={"39"})
    home = client.get("/").text
    m = re.search(r'<path d="[^"]*" fill="([^"]+)" fill-opacity="([^"]+)"'
                  r'[^>]*data-fips="39"', home)
    assert m, "Ohio path missing from the home map"
    assert m.group(1) == pay["39"]["f"]
    assert float(m.group(2)) == pay["39"]["o"]
    # a no-data state has the no-data tone; one outside the scope says so
    assert pay["04"]["f"].startswith("var(--map-nodata")
    assert "not fitted in this run" in pay["04"]["h"]


# ---------------------------------------- the emitter's own inert guard

def test_model_toggle_emitter_refuses_fewer_than_two_swappable_models():
    """The emitter drops models with no per-state fills and emits nothing
    with fewer than two left: never an inert control."""
    from app.core import usmap
    labels = {"ensemble": "FluBNF Ensemble categorical forecast", "pf": "Oracle SIHRS categorical forecast"}
    states = {"39": {"f": "#111111", "o": 0.8, "h": "x"}}
    # both models swappable: the toggle renders
    ok = usmap.model_toggle(
        ["ensemble", "pf"], labels, "ensemble",
        {"ensemble": {"states": states, "us": {}},
         "pf": {"states": states, "us": {}}})
    assert 'data-mmodel="ensemble"' in ok and 'data-mmodel="pf"' in ok
    # one model's payload is empty: no toggle at all, not a one-button row
    for empty in ({}, {"states": {}, "us": {}}):
        html = usmap.model_toggle(
            ["ensemble", "pf"], labels, "ensemble",
            {"ensemble": {"states": states, "us": {}}, "pf": empty})
        assert html == "", empty
    # a default that is itself unswappable falls to the first live model
    html = usmap.model_toggle(
        ["analogue", "ensemble", "pf"], labels, "analogue",
        {"analogue": {}, "ensemble": {"states": states, "us": {}},
         "pf": {"states": states, "us": {}}})
    assert 'data-mmodel="ensemble" aria-pressed="true"' in html
    assert 'data-mmodel="analogue"' not in html


def test_report_drops_models_whose_cards_carry_no_data(tmp_path):
    """Report twin of _outlook_models: a model with prob-less cards is
    dropped, leaving no toggle."""
    _synth_run_all_models(tmp_path)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    # strip every prob from the second model's cards
    for card in bundle["cards_by_model"]["analogue"].values():
        card.pop("probs", None)
    report_v2.render_bundle(bundle, tmp_path / "report2.html")
    html = (tmp_path / "report2.html").read_text()
    assert 'id="outlook-model"' not in html
    assert "data-mmodel=" not in html
    assert "Oracle SIHRS categorical forecast" in html                   # label stays honest
