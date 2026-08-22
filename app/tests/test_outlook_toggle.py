"""The outlook model toggle: one map, every available model.

The v3 inputs bundle carries hover cards for EACH available model
(ensemble, pf, analogue), all computed by the same quantile-CDF path
(categorical_probs_from_quantiles over the 23-level grid; the PF's samples
are reduced to that grid first). Home and the weekly report render the map
for the default model (ensemble when present) and, when the bundle carries
two or more models, add a compact aria-pressed toggle that swaps the fills,
hover cards, and the surface's model label client-side. Versioning stays
additive: a v1/v2 bundle renders its one model with no toggle and an
honest label, so the user's stored run from before per-model cards keeps
working exactly as it did.
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
from app.core import report_v2                      # noqa: E402

client = TestClient(srv.app)

OLD_MTIME = (1_000_000_000, 1_000_000_000)          # 2001: always stale


def _synth_run_all_models(workroot: Path):
    """Drive the real build path with synthetic PF samples, a vincentized
    ensemble, AND analogue quantiles for Ohio and the national row."""
    from app.core import ensemble as ens
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="all", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(7)
    pf_samples = {loc: {str(h): (rng.gamma(5.0, 20.0, 400) + 10 * h).tolist()
                        for h in (1, 2, 3, 4)}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    pf_q = {loc: ens.member_quantiles_from_samples(s)
            for loc, s in pf_samples.items()}
    # a deliberately different analogue: shifted samples, distinct grids
    an_q = {loc: ens.member_quantiles_from_samples(
                {h: (np.asarray(s[h]) * 0.7 + 25).tolist() for h in s})
            for loc, s in pf_samples.items()}
    ens_q = {loc: ens.vincentize({"pf": pf_q[loc], "analogue": an_q[loc]},
                                 weights=ens.equal_weights({"pf": 1,
                                                            "analogue": 1}))
             for loc in pf_samples}
    workroot.mkdir(parents=True, exist_ok=True)
    (workroot / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    outcome = {}
    srv._write_weekly_report(spec, workroot, pf_samples, obs,
                             pd.DataFrame(), locs, n2f, 42.0, outcome,
                             ens_q=ens_q, an_q=an_q)
    (workroot / "results.json").write_text(json.dumps({
        "forecast_date": "2098-01-03", "observed": obs,
        "models": {"ensemble": {loc: {h: {str(l): v for l, v in q.items()
                                          if str(l) in ("0.1", "0.25",
                                                        "0.5", "0.75",
                                                        "0.9")}
                                      for h, q in qd.items()}
                                for loc, qd in ens_q.items()}}}))
    return {"pf_samples": pf_samples, "an_q": an_q, "ens_q": ens_q,
            "pf_q": pf_q, "obs": obs, "outcome": outcome}


# ---------------------------------------------------- the v3 bundle itself

def test_bundle_v3_carries_every_model_via_the_one_quantile_cdf_path(
        tmp_path):
    from app.core.report import categorical_probs_from_quantiles
    parts = _synth_run_all_models(tmp_path)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["version"] == 3
    assert bundle["cards_model"] == "ensemble"      # the submitted forecast
    cbm = bundle["cards_by_model"]
    assert set(cbm) == {"ensemble", "pf", "analogue"}
    # every model's Ohio card equals the SAME quantile-CDF computation on
    # that model's own grid -- the pf card included (samples reduced to
    # the grid first, never the few-values-as-samples stand-in)
    lo = parts["obs"]["Ohio"][-1][1]
    from flubnf.settings import load_locations
    locs = load_locations()
    pop = int(dict(zip(locs.location_name,
                       locs.population.astype(float)))["Ohio"])
    for model, q in (("ensemble", parts["ens_q"]), ("pf", parts["pf_q"]),
                     ("analogue", parts["an_q"])):
        expect = categorical_probs_from_quantiles(q["Ohio"]["1"], lo, pop, 1)
        got = cbm[model]["OH"]["probs"]
        for c in expect:
            assert abs(got[c] - expect[c]) < 1e-9, (model, c)
        assert cbm[model]["OH"]["fips"] == "39"
    # the models disagree (the toggle switches real computations)
    assert cbm["analogue"]["OH"]["probs"] != cbm["ensemble"]["OH"]["probs"]
    # per-model national cards ride along; the primary stays back-compat
    assert set(bundle["national_map_cards"]) == {"ensemble", "pf",
                                                 "analogue"}
    assert bundle["national_map_card"] == \
        bundle["national_map_cards"]["ensemble"]
    # legacy fields unchanged for older readers
    assert "OH" in bundle["cards"] and bundle["details"]


# ------------------------------------------------------- the weekly report

def test_report_renders_the_toggle_with_every_bundled_model(tmp_path):
    _synth_run_all_models(tmp_path)
    html = (tmp_path / "report.html").read_text()
    # the compact aria-pressed toggle, above the map, default ensemble
    assert 'id="outlook-model"' in html
    assert html.index('id="outlook-model"') < html.index('id="map-anchor"')
    assert ('data-mmodel="ensemble" aria-pressed="true"') in html
    assert ('data-mmodel="pf" aria-pressed="false"') in html
    assert ('data-mmodel="analogue" aria-pressed="false"') in html
    for label in ("NAU ensemble outlook", "PF-SIHRS outlook",
                  "Calendar analogue outlook"):
        assert label in html, label
    # the label elements the swap script retargets
    assert html.count("data-mapmodel-label") >= 2
    # the swap payload and mechanics: per-state fills by fips, the
    # national group, and the honest click affordance
    assert "path[data-fips]" in html and 'data-fips="39"' in html
    assert "g.nat" in html
    assert "aria-pressed', String(on)" in html


def test_pf_only_run_gets_no_toggle_and_an_honest_label(tmp_path):
    """One available model = nothing to toggle: the map renders PF with
    the PF label, exactly as before."""
    from flubnf.settings import load_locations
    locs = load_locations()
    n2f = dict(zip(locs.location_name, locs.location.str.zfill(2)))
    spec = runs_mod.RunSpec(engine="pf", forecast_date="2098-01-03",
                            locations=["Ohio", "US"])
    rng = np.random.default_rng(3)
    pf_samples = {loc: {str(h): (rng.gamma(5.0, 20.0, 300) + 8 * h).tolist()
                        for h in (1, 2, 3, 4)}
                  for loc in ("Ohio", "US")}
    obs = {loc: [[f"2097-12-{d:02d}", 100.0 + d] for d in (6, 13, 20, 27)]
           for loc in ("Ohio", "US")}
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cells.json").write_text(json.dumps(
        [{"location": "Ohio", "last_observed": 127.0},
         {"location": "US", "last_observed": 127.0}]))
    srv._write_weekly_report(spec, tmp_path, pf_samples, obs,
                             pd.DataFrame(), locs, n2f, 42.0, {})
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    assert bundle["cards_model"] == "pf"
    assert set(bundle["cards_by_model"]) == {"pf"}
    html = (tmp_path / "report.html").read_text()
    assert 'id="outlook-model"' not in html
    assert "data-mmodel=" not in html
    assert "PF-SIHRS outlook" in html


def test_v2_bundle_rebuilds_with_no_toggle_and_the_stored_label(
        tmp_path, monkeypatch):
    """The user's stored run predates per-model cards: additive
    versioning means it rebuilds exactly as before -- one model, no
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
    assert "NAU ensemble outlook" in r.text          # the label stays honest


# ------------------------------------------------------------- the home map

def _latest(tmp_path, monkeypatch):
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path)
    w = tmp_path / "workroots" / "20980103T000000-abcdef"
    parts = _synth_run_all_models(w)
    srv._invalidate_scans()
    return w, parts


def test_home_outlook_gets_the_same_toggle(tmp_path, monkeypatch):
    w, _ = _latest(tmp_path, monkeypatch)
    by_model = srv._outlook_models(w.name)
    assert set(by_model) == {"ensemble", "pf", "analogue"}
    assert "39" in by_model["analogue"]              # fips-keyed, with data
    home = client.get("/").text
    assert 'id="outlook-model"' in home
    assert 'data-mmodel="ensemble" aria-pressed="true"' in home
    assert 'data-mmodel="analogue" aria-pressed="false"' in home
    # the toggle sits above the rendered map
    assert home.index('id="outlook-model"') < home.index('id="usmap"')
    # the label span is the relabel target and defaults to the ensemble
    assert 'data-mapmodel-label>NAU ensemble outlook' in home
    assert "Calendar analogue outlook" in home


def test_home_shows_no_toggle_for_a_pre_v3_bundle(tmp_path, monkeypatch):
    w, _ = _latest(tmp_path, monkeypatch)
    b = w / report_v2.BUNDLE_NAME
    bundle = json.loads(b.read_text())
    bundle["version"] = 2
    bundle.pop("cards_by_model", None)
    bundle.pop("national_map_cards", None)
    b.write_text(json.dumps(bundle))
    srv._invalidate_scans()
    assert srv._outlook_models(w.name) == {}
    home = client.get("/").text
    assert 'id="outlook-model"' not in home
    assert "data-mmodel=" not in home
    # the map and its honest one-model label render exactly as before
    assert 'id="usmap"' in home
    assert "NAU ensemble outlook" in home


def test_swap_payload_matches_the_server_render(tmp_path, monkeypatch):
    """The client-side swap must recolor with exactly the computation the
    server render used: payload fill/opacity for the default model equal
    the fills svg_map rendered."""
    import re
    from app.core import usmap
    w, _ = _latest(tmp_path, monkeypatch)
    by_model = srv._outlook_models(w.name)
    pay = usmap.state_swap_payload(by_model["ensemble"])
    home = client.get("/").text
    m = re.search(r'<path d="[^"]*" fill="([^"]+)" fill-opacity="([^"]+)"'
                  r'[^>]*data-fips="39"', home)
    assert m, "Ohio path missing from the home map"
    assert m.group(1) == pay["39"]["f"]
    assert float(m.group(2)) == pay["39"]["o"]
    # a no-data state carries the explicit no-data tone in the payload too
    assert pay["04"]["f"].startswith("var(--map-nodata")
    assert "no reported data" in pay["04"]["h"]


# ---------------------------------------- the emitter's own inert guard

def test_model_toggle_emitter_refuses_fewer_than_two_swappable_models():
    """User report 2026-08-21 (a toggle-like control above the outlook map
    that did nothing): the emitter now enforces the two-swappable-models
    contract itself. A model whose payload carries no per-state fills is
    dropped -- its button could only sit inert -- and with fewer than two
    left, nothing is emitted at all: a pre-v3 or partial bundle renders
    label only, never a dead control."""
    from app.core import usmap
    labels = {"ensemble": "NAU ensemble outlook", "pf": "PF-SIHRS outlook"}
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
    """The report-side twin of the server's _outlook_models bar: a v3-shaped
    bundle whose extra model carries only prob-less cards renders no
    toggle (the one real model, label only), never an inert button."""
    _synth_run_all_models(tmp_path)
    bundle = json.loads((tmp_path / report_v2.BUNDLE_NAME).read_text())
    # strip every prob from two of the three models' cards
    for m in ("pf", "analogue"):
        for card in bundle["cards_by_model"][m].values():
            card.pop("probs", None)
    report_v2.render_bundle(bundle, tmp_path / "report2.html")
    html = (tmp_path / "report2.html").read_text()
    assert 'id="outlook-model"' not in html
    assert "data-mmodel=" not in html
    assert "NAU ensemble outlook" in html            # label stays honest
