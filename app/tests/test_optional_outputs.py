"""The two optional FluSight outputs (knobs output.horizon_minus1 and
output.rate_change_pmf), off by default.

What is held here:
  * a default run writes the same bytes as before the knobs existed: the
    CSVs of a console run (the real Groundhog, the real Oracle step and
    floor, the PF faked) hash to what commit ac6b620 wrote;
  * with the knobs on, the files carry horizon -1 and the rate-change pmf
    exactly as the hub defines them, pass every hub check, keep the hub
    names, and record the choice in the spec;
  * the categories are the hub's scoring code's (checked against its own
    oracle output when a hub clone is present).

No hub needed: the hubfiles fixture of test_oracle_step builds a tiny
vintage and locations table.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import categorical as cat                      # noqa: E402
from app.core import horizons as hz                          # noqa: E402

from test_oracle_step import ASOF, hubfiles                  # noqa: E402,F401

#: sha256 of the two CSVs a default run of `_default_run` wrote at commit
#: ac6b620, before the optional outputs existed (computed by running this
#: harness on that commit's tree)
BASE_SHA = {
    "NAU_PyBNF-OracleSIHRS":
        "d4325a424fe437919884a07b82ac120eb02ea003d8cf2834e200895dfed25f0d",
    "NAU_PyBNF-GroundHogCGR":
        "601a20c24af9e9dd7c3cc5af542625a8850dfd5bf541d7c352b69df40644bae5",
}


#: both optional outputs on
ON = {"output.horizon_minus1": True, "output.rate_change_pmf": True}


def _pf_samples(names, n=400, seed=5) -> dict:
    """collect()'s shape, the anchor under ORIGIN, around each state's
    level in the synthetic vintage."""
    rng = np.random.default_rng(seed)
    out = {}
    for i, loc in enumerate(names):
        x0 = rng.gamma(40.0, 2.0 + 0.3 * i, n)
        out[loc] = {hz.ORIGIN: x0.tolist(),
                    **{h: (x0 * np.exp(0.06 * (int(h) + 1) * (1 - i % 2 * 2))
                           * rng.lognormal(0, 0.08 * (int(h) + 1), n)).tolist()
                       for h in hz.HORIZONS}}
    return out


@pytest.fixture
def pipeline_env(hubfiles, tmp_path, monkeypatch):
    """pipeline._run_all on the synthetic vintage: the PF faked (collect()
    returns fixed draws), the Groundhog, the Oracle step and the output
    floor real."""
    import app.core.data as core_data
    import app.core.engines.analogue as an_engine
    import app.core.engines.pf as pf_engine
    import app.core.runs as runs_mod
    import app.core.scoring as scoring_mod
    import flubnf.settings as fs
    from app.ui import pipeline as P
    from app.ui import shared as ui_shared
    from app.ui import state as ui_state
    from app.ui import versions as V
    from flubnf import bank as BK
    loc, vf = hubfiles["locations"], hubfiles["vintage"]
    aux = hubfiles["aux"]
    # the Groundhog's FluSurv-NET pool: the fixture's synthetic bank (the
    # committed one shares no season with a 2090s vintage)
    monkeypatch.setattr(BK, "read", lambda stream, *a, **k: (
        aux["bank"], aux["manifest"]))
    monkeypatch.setattr(runs_mod, "APP_STATE", tmp_path / "state")
    monkeypatch.setattr(fs, "LOCATIONS", loc)
    monkeypatch.setattr(an_engine, "LOCATIONS", loc)
    monkeypatch.setattr(an_engine, "vintage_path", lambda d: vf)
    monkeypatch.setattr(core_data, "vintage_path", lambda d: vf)
    names = ["Ohio", "Utah", "California", "Texas"]
    raw = _pf_samples(names)
    monkeypatch.setattr(P, "_pf_engine_state", lambda: "ready")
    monkeypatch.setattr(pf_engine, "prepare", lambda spec, w: [])
    monkeypatch.setattr(pf_engine, "execute",
                        lambda w: {f"{n}_r0": "ok" for n in names})
    monkeypatch.setattr(pf_engine, "collect",
                        lambda w: {l: {h: list(v) for h, v in s.items()}
                                   for l, s in raw.items()})

    def _no_truth():
        raise RuntimeError("no truth in this test")
    monkeypatch.setattr(scoring_mod, "load_truth", _no_truth)
    monkeypatch.setattr(P, "_sleep_guard", lambda: None)
    monkeypatch.setattr(V, "_engine_versions_for_ledger", lambda e: {})
    monkeypatch.setattr(P, "_harvest_params", lambda w: {})
    monkeypatch.setattr(P, "_write_weekly_report", lambda *a, **k: None)
    monkeypatch.setattr(P, "_archive_run", lambda w, d: "archived")
    status_before = dict(ui_state._status)
    yield {"names": names, "raw": raw, "vintage": vf, "locations": loc}
    ui_state._status.clear()
    ui_state._status.update(status_before)
    ui_shared._invalidate_scans()


def _default_run(names, knobs=None, **spec_kw):
    """One console run as the route builds it; (spec, outcome)."""
    from app.core.runs import Ledger, RunSpec
    from app.ui import pipeline as P
    from app.ui.routes import forecast as F
    extra = F._run_extra(2, "vintage")
    if knobs:
        from app.core import knobs as K
        K.write_extra(knobs, extra)
    spec = RunSpec(engine="all", forecast_date=ASOF, locations=names,
                   replicates=1, extra=extra, **spec_kw)
    P._run_all(spec)
    row = next(iter(Ledger().rows(1)))
    return spec, json.loads(row.get("outcome") or "{}")


def _sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_a_default_run_writes_the_same_bytes_as_before(pipeline_env):
    spec, out = _default_run(pipeline_env["names"])
    assert "submissions" in out and not out.get("submission_errors"), out
    got = {mid: _sha(p) for mid, p in out["submissions"].items()}
    if os.environ.get("R4_PRINT_SHA"):
        print("BASE_SHA", json.dumps(got))
    assert set(got) == set(BASE_SHA)
    assert got == BASE_SHA
    # the same bytes on Windows: LF line endings, never os.linesep
    for p in out["submissions"].values():
        assert b"\r" not in Path(p).read_bytes(), p


# ------------------------------------------------ the categories

@pytest.mark.parametrize("pop", [300_000, 578_000, 3_400_000, 5_157_699,
                                 10_000_000, 39_431_263, 340_110_988])
@pytest.mark.parametrize("h", [0, 1, 2, 3])
def test_the_integer_bins_are_the_hubs_case_when(pop, h):
    """bins() (read by every CDF) and category() (the hub scoring code's
    rule, applied to one change) agree on every whole count change."""
    s, big = cat.bins(pop, h)
    span = max(3 * big, 40)
    for d in range(-span, span + 1):
        want = cat.category(d, pop, h)
        if abs(d) <= s:
            got = "stable"
        elif d > 0:
            got = "large_increase" if d >= big else "increase"
        else:
            got = "large_decrease" if d <= -big else "decrease"
        assert got == want, (pop, h, d, s, big)


def test_a_change_of_exactly_ten_is_not_stable():
    """The hub: stable when the count change is BELOW 10. The categories
    read +10 as stable until this change (the CDF was read at the cut)."""
    assert cat.category(10, 500_000, 0) == "large_increase"
    assert cat.category(9, 500_000, 0) == "stable"
    assert cat.category(-10, 500_000, 0) == "large_decrease"
    p = cat.probs_from_samples(np.full(100, 110.0), 100.0, 500_000, 0)
    assert p["large_increase"] == 1.0 and p["stable"] == 0.0
    # a draw of 109.6 is the count 110
    p = cat.probs_from_samples(np.full(100, 109.6), 100.0, 500_000, 0)
    assert p["large_increase"] == 1.0


def test_pathwise_changes_carry_the_baselines_uncertainty():
    from app.core import optional_outputs as OPT
    rng = np.random.default_rng(2)
    base = rng.normal(400, 60, 4000)
    s = {hz.ORIGIN: base.tolist(),
         **{h: (base + 5).tolist() for h in hz.HORIZONS}}
    # every path rises by 5 from its own as-of week: stable, whatever the
    # spread of the level
    by_path = OPT.pf_rate_change(s, None, 5_000_000, k=1)
    assert set(by_path) == {0, 1, 2, 3}
    assert all(p["stable"] == 1.0 for p in by_path.values())
    # against one reported count the same draws spread over the categories
    vs_report = OPT.pf_rate_change(s, 400.0, 5_000_000, k=0)
    assert vs_report[0]["stable"] < 0.5


def test_pmf_values_are_four_decimals_summing_to_one():
    from app.core import submit as SB
    rng = np.random.default_rng(4)
    for _ in range(500):
        p = rng.dirichlet(np.full(5, 0.3))
        vals = SB.pmf_values(dict(zip(cat.CATS, p)), cat.CATS)
        assert all(len(v.split(".")[1]) <= 4 for v in vals)
        assert sum(float(v) for v in vals) == pytest.approx(1.0, abs=1e-12)
        assert min(float(v) for v in vals) >= 0
    with pytest.raises(ValueError, match="not a distribution"):
        SB.pmf_values({"stable": 0.9}, cat.CATS)


# ------------------------------------------------ the knobs

def test_the_knobs_are_off_by_default_and_never_mark_a_run_modified():
    from app.core import knobs as K
    from app.core.runs import RunSpec, model_settings_label, spec_settings
    assert K.resolve({"output.horizon_minus1": "0",
                      "output.rate_change_pmf": "off"}, "all",
                     forecast_date=ASOF) == {}
    nd = K.resolve({"knob.output.horizon_minus1": "1",
                    "knob.output.rate_change_pmf": "on"}, "all",
                   forecast_date=ASOF)
    assert nd == ON
    spec = RunSpec("all", ASOF, extra=K.write_extra(nd, {}))
    assert spec.extra["knobs"] == ON                    # recorded in the spec
    assert not K.modified(spec) and K.hub_names(spec)
    assert model_settings_label(spec) == ""
    assert dict(spec_settings(spec))["optional hub rows"] == (
        "Horizon -1 rows, Rate-change rows")
    assert "optional hub rows" not in dict(spec_settings(RunSpec("all", ASOF)))
    # with a model knob beside them the run is modified, as ever
    both = K.write_extra({**nd, "oracle.w": 0.25}, {})
    assert K.modified(RunSpec("all", ASOF, extra=both))
    # a retrospective writes no files: refused there
    with pytest.raises(K.KnobError, match="retrospective"):
        K.resolve({"output.rate_change_pmf": "1"}, "all", scope="retro",
                  forecast_date=ASOF)


def test_the_panel_offers_them_with_a_plain_tip():
    from app.core import knobs as K
    p = K.panel("forecast", {"output.horizon_minus1": "1"})
    rows = {r["key"]: r for g in p["groups"] for r in g["rows"]}
    for key in K.OPTIONAL_KEYS:
        r = rows[key]
        assert r["optional"] and r["kind"] == "bool" and r["default"] == "0"
        assert r["tip"].startswith("Optional;")
        assert r["name"] == "knob." + key
    assert "the hub never scores it" in rows["output.horizon_minus1"]["tip"]
    assert rows["output.horizon_minus1"]["value"] == "1"
    assert p["modified"] is False                  # rows only, not the model
    retro = K.panel("retro")
    assert not K.OPTIONAL_KEYS & {r["key"] for g in retro["groups"]
                                  for r in g["rows"]}


def test_the_settings_panel_renders_them():
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    html = TestClient(srv.app).get("/forecast").text
    for key in ("output-horizon_minus1", "output-rate_change_pmf"):
        i = html.index(f'id="ks-{key}"')
        tag = html[html.rindex("<select", 0, i):html.index(">", i)]
        assert 'data-optional="1"' in tag
    assert "Optional; the hub never scores it." in html


# ------------------------------------------------ a run with the knobs on

def _frame(path):
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def test_a_run_with_both_knobs_writes_what_the_hub_defines(pipeline_env):
    from app.core import hubcheck as HC
    from app.core import submit as SB
    names = pipeline_env["names"]
    _, off = _default_run(names)
    spec, out = _default_run(names, knobs=ON)
    assert not out.get("submission_errors"), out
    assert set(out["submissions"]) == set(off["submissions"])   # hub names
    assert "knobs" not in out                  # the model is as shipped
    assert spec.extra["knobs"] == ON
    ref = SB.hub_reference_date(ASOF)
    for mid, path in out["submissions"].items():
        res = HC.check_file(path)
        assert not HC.failures(res), (mid, HC.failures(res))
        d = _frame(path)
        base = _frame(off["submissions"][mid])
        # the required rows are the default file's, cell for cell
        req = d[(d.target == "wk inc flu hosp") & (d.horizon != "-1")]
        assert req.reset_index(drop=True).equals(base)
        pmf = d[d.target == SB.RATE_CHANGE_TARGET]
        assert set(pmf.output_type) == {"pmf"}
        assert sorted(set(pmf.horizon)) == ["0", "1", "2", "3"]
        for (_, h), g in pmf.groupby(["location", "horizon"]):
            assert list(g.output_type_id) == list(cat.CATS)
            assert abs(g.value.astype(float).sum() - 1) < 1e-12
            assert set(g.target_end_date) == {
                str((ref + pd.Timedelta(weeks=int(h))).date())}
        m1 = d[d.horizon == "-1"]
        if mid.endswith("OracleSIHRS"):
            # every location's as-of week, from the anchor draws
            assert m1.location.nunique() == len(names)
            assert set(m1.target_end_date) == {ASOF}
            assert (m1.groupby("location").output_type_id.count() == 23).all()
            assert pmf.location.nunique() == len(names)
        else:
            # the Groundhog's anchor is the as-of week: nothing to give
            assert m1.empty
            assert "no horizon -1 rows" in out["optional_rows"][mid]["why"]
            assert pmf.location.nunique() == base.location.nunique()
    assert out["optional_rows"]["NAU_PyBNF-OracleSIHRS"] == {
        "horizon -1": len(names), "rate change": len(names)}


def test_a_real_time_run_on_the_live_file_writes_the_same_rows(
        pipeline_env, monkeypatch):
    """Submission day: the hub's live target file holds the as-of week and
    the dated archive copy does not exist yet (it is added by hand, days
    later). The optional rows read the file the run read, so they are the
    rows an archived run of the same data writes, rate change included."""
    import app.core.data as core_data
    import app.core.engines.analogue as an_engine
    import app.core.oracle as oracle_mod
    names = pipeline_env["names"]
    _, archived = _default_run(names, knobs=ON)
    got_archived = {m: _sha(p) for m, p in archived["submissions"].items()}

    def _no_vintage(d):
        raise FileNotFoundError(f"No vintage for {d}")
    for mod in (core_data, an_engine, oracle_mod):
        monkeypatch.setattr(mod, "vintage_path", _no_vintage)
    monkeypatch.setattr(core_data, "live_path",
                        lambda: pipeline_env["vintage"])
    from app.core.runs import Ledger, RunSpec
    from app.core import knobs as K
    from app.ui import pipeline as P
    from app.ui.routes import forecast as F
    extra = F._run_extra(2, "realtime")
    K.write_extra(ON, extra)
    P._run_all(RunSpec(engine="all", forecast_date=ASOF, locations=names,
                       replicates=1, extra=extra))
    live = json.loads(next(iter(Ledger().rows(1))).get("outcome") or "{}")
    assert live["data_source"]["kind"] == "live", live
    assert not live.get("submission_errors"), live
    assert live["optional_rows"] == archived["optional_rows"]
    assert {m: _sha(p) for m, p in live["submissions"].items()} == \
        got_archived


def test_the_groundhog_forecasts_the_as_of_week_when_it_did_not_see_it(
        pipeline_env):
    """Same-day week treated as unreported: both anchors move a week back,
    the Groundhog forecasts the as-of week (horizon -1) from its donors,
    and writes no rate change (its quantiles carry no path to the
    baseline week); the PF reads the change along its paths."""
    from app.core import hubcheck as HC
    from app.core import knobs as K
    names = pipeline_env["names"]
    spec, out = _default_run(names, knobs={**ON, "run.drop_same_day": True},
                             drop_same_day=True)
    assert not out.get("submission_errors"), out
    assert K.modified(spec)            # the same-day knob changes the model
    assert len(out["submissions"]) == 2
    for mid, path in out["submissions"].items():
        # <hub id>-modified is not a hub name: the rows are checked, as the
        # writer's gate checks them
        assert not HC.failures(HC.check_frame(HC.read_text_frame(path))), mid
        d = _frame(path)
        m1 = d[d.horizon == "-1"]
        pmf = d[d.target == "wk flu hosp rate change"]
        assert m1.location.nunique() > 0 and set(m1.target_end_date) == {ASOF}
        if "GroundHogCGR" in mid:
            assert pmf.empty
        else:
            assert pmf.location.nunique() == len(names)


def test_a_quantile_grids_tails_never_reach_an_impossible_change():
    """Beyond the 1 and 99 percent levels the grid's outermost segments
    carry on to levels 0 and 1 (never below a count of 0): a summer grid
    far from every large cut puts nothing there, where clamping the CDF
    at the outermost levels put 1 percent in each large category."""
    from app.core.submit import QUANTILES
    grid = {L: 40.0 + 20.0 * (L - 0.5) for L in QUANTILES}
    p = cat.probs_from_quantiles(grid, 40.0, 39_431_263, 0)
    assert p["large_decrease"] == 0.0 and p["large_increase"] == 0.0
    assert p["stable"] == pytest.approx(1.0)
    # a grid hugging zero: its lower tail stops at a count of 0
    low = {L: 3.0 * L for L in QUANTILES}
    p = cat.probs_from_quantiles(low, 40.0, 300_000, 0)
    assert p["large_decrease"] == pytest.approx(1.0)
