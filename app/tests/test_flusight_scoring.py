"""FluSight's scored-cell rule, the figures scored beside WIS, and the
replay's output floor.

Pinned:
  * THE cell rule (scoring.cell_scored): settled truth (0 included), a
    forecast with finite quantiles (a median of 0 included), a baseline
    cell. Every scorer uses it.
  * per-cell metrics: log-scale WIS and 50/80/95 coverage beside WIS, the
    baseline's log-scale WIS on the same cell; scores.json carries them
    with a version (retro.SCORES_V), and an older file is stale for a live
    root, so finalize_season rescores it.
  * the data contract: playback stats (playback.STATS_FIELDS),
    retro.run_summary's headline figures, retro.state_metrics,
    UsNational's log and coverage figures, relwis ratio figures' detail.
    Every reader takes a file without the new columns (a sealed root) as
    None.
  * the replay applies the console's output floor to both members before
    storage and records it in the season's run record.
"""
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import horizons as hz                      # noqa: E402
from app.core import playback, relwis, retro, scoring    # noqa: E402
from app.core import us_national as usn                  # noqa: E402
from app.core.floor import floor_quantiles, floor_samples  # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL    # noqa: E402
# the season page's route fixture (sealed and live trees, stubbed truth)
from test_retro_pf_name import world                     # noqa: E402,F401

SEASON = "2098-99"
W1 = "2098-11-07"
N2F = {"Ohio": "39", "Utah": "49"}


def _flat(v):
    """A 23-level forecast of the single value v (a point mass)."""
    return {float(L): float(v) for L in QL}


def _fan(center, spread=10.0):
    return {float(L): center + (float(L) - 0.5) * spread for L in QL}


# ------------------------------------------------------------ the cell rule

def test_the_rule_scores_a_truth_of_zero_and_a_median_of_zero():
    zero = _flat(0.0)
    assert scoring.cell_scored(zero, 0.0, 1.0)         # both zero: scored
    assert scoring.cell_scored(zero, 5.0, 1.0)         # a zero forecast
    assert scoring.cell_scored(_fan(20.0), 0.0, 1.0)   # a zero truth
    assert scoring.cell_scored(zero, 0.0, 0.0)         # a baseline WIS of 0
    # what is not a cell: no settled truth, no baseline, no usable forecast
    assert not scoring.cell_scored(zero, None, 1.0)
    assert not scoring.cell_scored(zero, float("nan"), 1.0)
    assert not scoring.cell_scored(zero, -1.0, 1.0)
    assert not scoring.cell_scored(zero, 5.0, None)
    assert not scoring.cell_scored(zero, 5.0, float("nan"))
    assert not scoring.cell_scored({**zero, 0.9: float("nan")}, 5.0, 1.0)
    assert not scoring.cell_scored({0.4: 1.0, 0.6: 2.0}, 5.0, 1.0)
    assert not scoring.cell_scored({}, 5.0, 1.0)
    assert not scoring.cell_scored(None, 5.0, 1.0)


def test_every_scorer_uses_the_one_rule():
    """No scorer restates the earlier guards (truth > 0, median > 0)."""
    core = Path(scoring.__file__).resolve().parent
    for mod in ("scoring.py", "retro.py", "playback.py", "site_build.py",
                "groundhog.py", "custom_run.py", "custom_retro.py"):
        src = (core / mod).read_text()
        assert "actual <= 0" not in src, mod
        assert "[0.5] <= 0" not in src and "get(0.5, 0) <= 0" not in src, mod


def test_cell_metrics_of_a_point_mass():
    """A point forecast's WIS is |y - m| on each scale; it covers only its
    own value."""
    m = scoring.cell_metrics(_flat(0.0), 10.0)
    assert m["wis"] == pytest.approx(10.0)
    assert m["log_wis"] == pytest.approx(math.log(11.0))
    assert (m["cov50"], m["cov80"], m["cov95"]) == (0, 0, 0)
    m = scoring.cell_metrics(_flat(0.0), 0.0)
    assert (m["wis"], m["log_wis"]) == (0.0, 0.0)
    assert (m["cov50"], m["cov80"], m["cov95"]) == (1, 1, 1)
    # a quantile set that gives no WIS is no cell
    assert scoring.cell_metrics({0.5: 1.0}, 1.0) is None


def _stub_baselines(monkeypatch, mod=scoring, wis=2.0, log=0.5):
    monkeypatch.setattr(mod, "_baseline_cells",
                        lambda d, fips, tr: {(f, d, h): wis for f in fips
                                             for h in range(4)})
    monkeypatch.setattr(mod, "_baseline_log_cells",
                        lambda d, fips, tr: {(f, d, h): log for f in fips
                                             for h in range(4)})


def test_scored_rows_carry_the_metrics_and_the_baselines_log_score(
        monkeypatch):
    _stub_baselines(monkeypatch)
    T = pd.Timestamp(W1)
    truth = {("39", T + pd.Timedelta(days=7 * (h + 1))): v
             for h, v in enumerate((0.0, 10.0, 20.0, 30.0))}
    df = scoring.score_quantiles({"Ohio": {h: _flat(0.0)
                                           for h in hz.HORIZONS}},
                                 W1, N2F, truth)
    assert list(df.horizon) == [0, 1, 2, 3]            # truth 0 and median 0
    for c in scoring.METRIC_COLUMNS + ("base_wis", "base_log_wis", "rel"):
        assert c in df.columns, c
    assert list(df.wis) == pytest.approx([0.0, 10.0, 20.0, 30.0])
    assert list(df.log_wis) == pytest.approx(
        [math.log(1 + v) for v in (0.0, 10.0, 20.0, 30.0)])
    assert list(df.cov95) == [1, 0, 0, 0]
    assert (df.base_log_wis == 0.5).all() and (df.base_wis == 2.0).all()


def test_the_baseline_gives_wis_and_log_wis_on_the_same_cells(
        tmp_path, monkeypatch):
    """One read of the hub's FluSight-baseline file gives both scales; a
    truth of 0 is a baseline cell too."""
    import flubnf.settings as fs
    from flubnf.wis import log_wis, wis
    hub = tmp_path / "hub"
    d = hub / "model-output" / "FluSight-baseline"
    d.mkdir(parents=True)
    ref = (pd.Timestamp(W1) + pd.Timedelta(days=7)).date()
    rows = ["reference_date,horizon,target,target_end_date,location,"
            "output_type,output_type_id,value"]
    for h in range(4):
        ted = (pd.Timestamp(ref) + pd.Timedelta(days=7 * h)).date()
        rows += [f"{ref},{h},wk inc flu hosp,{ted},39,quantile,{L},{v}"
                 for L, v in _fan(100.0, 20.0).items()]
    (d / f"{ref}-FluSight-baseline.csv").write_text("\n".join(rows) + "\n")
    monkeypatch.setattr(fs, "HUB", hub)
    truth = {("39", pd.Timestamp(ref) + pd.Timedelta(days=7 * h)): v
             for h, v in enumerate((90.0, 0.0, 100.0, 130.0))}
    b = scoring._baseline_cells(W1, {"39"}, truth)
    lb = scoring._baseline_log_cells(W1, {"39"}, truth)
    q = _fan(100.0, 20.0)
    for h, y in enumerate((90.0, 0.0, 100.0, 130.0)):
        assert b[("39", W1, h)] == pytest.approx(wis(q, y).wis)
        assert lb[("39", W1, h)] == pytest.approx(log_wis(q, y))
    # read again without the preceding WIS call: the same numbers
    scoring._LOG_SLOT.clear()
    assert scoring._baseline_log_cells(W1, {"39"}, truth) == pytest.approx(lb)
    # no baseline: the log figures are absent, never an error
    monkeypatch.setattr(fs, "HUB", tmp_path / "nohub")
    scoring._LOG_SLOT.clear()
    assert scoring._baseline_log_cells(W1, {"39"}, truth) == {}


def test_pooled_metrics_are_ratios_of_sums_and_fractions_of_cells():
    df = pd.DataFrame({"wis": [1.0, 3.0], "base_wis": [2.0, 2.0],
                       "log_wis": [0.2, 0.4], "base_log_wis": [0.3, 0.3],
                       "cov50": [1, 0], "cov80": [1, 0], "cov95": [1, 1]})
    pm = scoring.pooled_metrics(df)
    assert pm["rel"] == pytest.approx(1.0)
    assert pm["log_rel"] == pytest.approx(1.0)
    assert pm["cov"] == pytest.approx({"50": 0.5, "80": 0.5, "95": 1.0})
    assert pm["n"] == 2
    # a file from before the log and coverage columns: None, not a crash
    old = scoring.pooled_metrics(df[["wis", "base_wis"]])
    assert old["rel"] == pytest.approx(1.0)
    assert old["log_rel"] is None and old["cov"] is None
    # a missing baseline log score on any cell: no log figure at all
    part = df.assign(base_log_wis=[0.3, np.nan])
    assert scoring.pooled_metrics(part)["log_rel"] is None
    assert scoring.pooled_metrics(df[:0]) == {"rel": None, "log_rel": None,
                                              "cov": None, "n": 0}


# ------------------------------------------------------- the season's scores

def _season(tmp_path, pf=None, an=None) -> Path:
    """One stored week: pf draws (stored convention: "0" the anchor) and
    analogue quantiles, for Ohio and Utah."""
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    if pf is None:
        pf = {"Ohio": {str(h): [0.0] * 3 for h in range(5)},       # collapsed
              "Utah": {str(h): [49.0, 50.0, 51.0] for h in range(5)}}
    if an is None:
        an = {loc: {str(h): {str(L): v for L, v in _fan(50.0).items()}
                    for h in range(1, 5)} for loc in N2F}
    (wd / "samples.json").write_text(
        json.dumps({"asof": W1, "pf": pf, "analogue": an}))
    return root


def _truth(ohio=0.0, utah=50.0, us=100.0):
    t = {}
    for k in range(1, 5):
        d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
        t[("39", d)] = ohio
        t[("49", d)] = utah
        t[("US", d)] = us
    return t


@pytest.fixture
def stub(monkeypatch):
    truth = _truth()
    monkeypatch.setattr(scoring, "load_truth", lambda: (truth, dict(N2F)))
    monkeypatch.setattr(playback, "load_truth", lambda: (truth, dict(N2F)))
    _stub_baselines(monkeypatch)
    _stub_baselines(monkeypatch, playback)
    return truth


def test_a_season_is_scored_under_the_rule_with_a_version(tmp_path, stub):
    df = retro.score_season(_season(tmp_path), SEASON)
    # Ohio's truth is 0 and its pf forecast collapsed to 0: both scored now
    oh = df[(df.model == "pf") & (df.location == "Ohio")]
    assert len(oh) == 4 and (oh.wis == 0.0).all() and (oh.cov95 == 1).all()
    assert len(df[df.location == "Ohio"]) == 8        # the analogue's too
    assert set(df.columns) >= {"log_wis", "base_log_wis", "cov50", "cov80",
                               "cov95", retro.SCORES_V_COLUMN}
    assert (df[retro.SCORES_V_COLUMN] == retro.SCORES_V).all()
    assert retro.scores_frame_current(df)


def test_an_older_scores_file_is_stale_and_finalize_rescores_it(
        tmp_path, stub):
    root = _season(tmp_path)
    old = retro.score_season(root, SEASON).drop(
        columns=["log_wis", "base_log_wis", "cov50", "cov80", "cov95",
                 retro.SCORES_V_COLUMN])
    sf = root / "scores.json"
    old.to_json(sf)
    future = sf.stat().st_mtime + 60
    os.utime(sf, (future, future))                 # newer than every week
    assert not retro.scores_current(root)
    assert retro.scores_version(pd.read_json(sf)) == 1
    retro.finalize_season(root, SEASON)
    assert retro.scores_current(root)
    new = pd.read_json(sf)
    assert (new[retro.SCORES_V_COLUMN] == retro.SCORES_V).all()
    # an empty file scores nothing under either rule: not a version question
    assert retro.scores_frame_current(pd.DataFrame())


def test_run_summary_carries_the_headline_figures(tmp_path, stub):
    root = _season(tmp_path)
    df = retro.score_season(root, SEASON)
    df.to_json(root / "scores.json")
    retro._SUMMARY_CACHE.clear()
    s = retro.run_summary(root)
    for m in ("pf", "analogue"):
        g = df[df.model == m]
        assert s["headline_rels"][m] == pytest.approx(
            g.wis.sum() / g.base_wis.sum())
        assert s["headline_log_rels"][m] == pytest.approx(
            g.log_wis.sum() / g.base_log_wis.sum())
        assert s["headline_covs"][m]["95"] == pytest.approx(g.cov95.mean())
        assert set(s["headline_covs"][m]) == {"50", "80", "95"}
        assert s["headline_ns"][m] == len(g)
    # a sealed root's older file: relWIS as before, the rest None
    df[["model", "location", "fips", "asof", "horizon", "wis", "base_wis",
        "rel"]].to_json(root / "scores.json")
    os.utime(root / "scores.json", (1e10, 1e10))
    old = retro.run_summary(root)
    assert old["headline_rels"]["pf"] == pytest.approx(s["headline_rels"]["pf"])
    assert old["headline_log_rels"]["pf"] is None
    assert old["headline_covs"]["pf"] is None
    retro._SUMMARY_CACHE.clear()


def test_state_metrics_per_jurisdiction_with_us_left_out():
    rows = []
    for loc, w in (("Ohio", 1.0), ("Utah", 3.0), ("US", 50.0)):
        for h in range(2):
            rows.append({"model": "pf", "location": loc, "wis": w,
                         "base_wis": 2.0, "log_wis": w / 10,
                         "base_log_wis": 0.2, "cov50": h, "cov80": 1,
                         "cov95": 1})
    st = retro.state_metrics(pd.DataFrame(rows))
    assert set(st) == {"Ohio", "Utah"}
    assert st["Ohio"]["pf"]["rel"] == pytest.approx(0.5)
    assert st["Utah"]["pf"]["log_rel"] == pytest.approx(1.5)
    assert st["Ohio"]["pf"]["cov"] == pytest.approx(
        {"50": 0.5, "80": 1.0, "95": 1.0})
    assert st["Ohio"]["pf"]["n"] == 2


# ----------------------------------------------------------- the US figures

def test_the_us_row_carries_log_and_coverage_and_says_what_pf_is():
    rows = [{"model": "pf", "location": "US", "wis": 3.0, "base_wis": 2.0,
             "log_wis": 0.3, "base_log_wis": 0.2, "cov50": 0, "cov80": 1,
             "cov95": 1},
            {"model": "pf", "location": "Ohio", "wis": 1.0, "base_wis": 2.0}]
    us = usn.from_scores(pd.DataFrame(rows))
    d = us.as_dict()
    assert d["pf"] == pytest.approx(1.5)
    assert d["log_rel"]["pf"] == pytest.approx(1.5)
    assert d["cov"]["pf"] == {"50": 0.0, "80": 1.0, "95": 1.0}
    assert us.log_rel("pf") == pytest.approx(1.5)
    # the fitted pf US row never had the Oracle step, and says so; the
    # sum of states is a sum of Oracle SIHRS state forecasts
    assert "without the Oracle step" in d["pf_note"]
    assert usn.UsNational(usn.AGGREGATED).as_dict()["pf_note"] == ""


def test_the_national_aggregate_carries_log_and_coverage(tmp_path, stub):
    pf = {"Ohio": {str(h): [40.0, 60.0] for h in range(5)},
          "Utah": {str(h): [60.0, 40.0] for h in range(5)}}
    r = retro.national_aggregate(_season(tmp_path, pf=pf))
    # index-aligned draws sum to exactly the US truth, 100
    assert r["pf"] == 0.0 and r["cells"]["pf"] == 4
    assert r["log_rel"]["pf"] == 0.0
    assert r["cov"]["pf"] == {"50": 1.0, "80": 1.0, "95": 1.0}
    assert set(r["cov"]["analogue"]) == {"50", "80", "95"}
    assert r["log_rel"]["analogue"] > 0


# ------------------------------------------------------ the playback stats

def test_every_stats_entry_carries_the_contract(tmp_path, monkeypatch):
    from test_playback import SEASON as PB_SEASON, ASOF, _mk_root
    root = _mk_root(tmp_path, monkeypatch)
    monkeypatch.setattr(playback, "_baseline_log_cells",
                        lambda d, fips, tr: {(f, d, h): 0.5 for f in fips
                                             for h in range(4)})
    p = playback.build_week(root, PB_SEASON, ASOF)
    assert set(p["stats"]) == {"pf", "pf2s", "analogue", "FluSight-baseline"}
    for m, st in p["stats"].items():
        assert set(playback.STATS_FIELDS) <= set(st), m
        assert st["week_n"] == st["cum_n"] > 0, m
        assert st["week_log_rel"] is not None, m
        assert set(st["week_cov"]) == {"50", "80", "95"}, m
        assert all(0.0 <= v <= 1.0 for v in st["week_cov"].values()), m
    # the members: four horizons in each of two states
    assert p["stats"]["pf"]["week_n"] == 8
    # the baseline's file covers Ohio's first two horizons (US left out)
    assert p["stats"]["FluSight-baseline"]["week_n"] == 2


def test_stats_read_from_scores_json_and_tolerate_an_older_one(
        tmp_path, monkeypatch):
    import shutil
    from test_playback import SEASON as PB_SEASON, ASOF, _mk_root
    root = _mk_root(tmp_path, monkeypatch)
    # scored here from the stored week: two states, four horizons each
    fly = playback.build_week(root, PB_SEASON, ASOF)["stats"]["pf"]
    assert fly["week_n"] == 8 and fly["week_cov"] is not None
    rows = [{"model": "pf", "location": "Ohio", "asof": ASOF, "horizon": h,
             "wis": 4.0, "base_wis": 2.0, "log_wis": 0.3,
             "base_log_wis": 0.2, "cov50": h % 2, "cov80": 1, "cov95": 1,
             retro.SCORES_V_COLUMN: retro.SCORES_V} for h in range(4)]
    pd.DataFrame(rows).to_json(root / "scores.json")
    st = playback.build_week(root, PB_SEASON, ASOF)["stats"]["pf"]
    assert st["week_rel"] == pytest.approx(2.0)
    assert st["cum_log_rel"] == pytest.approx(1.5)
    assert st["week_cov"] == pytest.approx({"50": 0.5, "80": 1.0, "95": 1.0})
    assert (st["week_n"], st["cum_n"]) == (4, 4)
    # the sealed record's file (no version, none of the new columns) used
    # the earlier cell rule: the members are scored here like the officials,
    # so one table is one rule; the retired blend it alone holds is read
    # from it, with None for the new figures
    old = [{k: r[k] for k in ("model", "location", "asof", "horizon",
                              "wis", "base_wis")} for r in rows]
    old += [{**r, "model": "ensemble", "wis": 1.0} for r in old]
    pd.DataFrame(old).to_json(root / "scores.json")
    os.utime(root / "scores.json", (1e10, 1e10))
    stats = playback.build_week(root, PB_SEASON, ASOF)["stats"]
    assert stats["pf"] == fly
    assert stats["ensemble"]["week_rel"] == pytest.approx(0.5)
    assert stats["ensemble"]["week_log_rel"] is None
    assert stats["ensemble"]["cum_cov"] is None
    # a clone that cannot score a member (no baseline) falls back to the
    # stored record rather than show nothing
    shutil.rmtree(root / "playback_cache")
    monkeypatch.setattr(playback, "_baseline_cells",
                        lambda asof, fips_set, tr: {})
    st = playback.build_week(root, PB_SEASON, ASOF)["stats"]["pf"]
    assert st["week_rel"] == pytest.approx(2.0)
    assert st["week_log_rel"] is None and st["cum_cov"] is None
    assert st["week_n"] == 4


# ------------------------------------------------ the season page's figures

def test_ratio_figures_carry_log_and_coverage_per_member_and_state():
    rows = []
    for loc, fips, w in (("Ohio", "39", 1.0), ("Utah", "49", 3.0)):
        for h in range(2):
            rows.append({"model": "pf", "location": loc, "fips": fips,
                         "asof": W1, "horizon": h, "wis": w,
                         "base_wis": 2.0, "log_wis": w / 10,
                         "base_log_wis": 0.2, "cov50": h, "cov80": 1,
                         "cov95": 1, "rel": w / 2.0})
    figs = relwis.season_figures(pd.DataFrame(rows))
    assert figs.values["pf"] == pytest.approx(1.0)
    assert figs.detail["pf"]["log_rel"] == pytest.approx(1.0)
    assert figs.detail["pf"]["cov"] == pytest.approx(
        {"50": 0.5, "80": 1.0, "95": 1.0})
    ohio = next(r for r in figs.states if r["name"] == "Ohio")
    assert ohio["pf"] == pytest.approx(0.5)
    assert ohio["detail"]["pf"]["log_rel"] == pytest.approx(0.5)
    assert ohio["detail"]["pf"]["cov"]["95"] == 1.0
    # an older frame: the same relWIS, no log or coverage figures
    old = pd.DataFrame(rows).drop(columns=["log_wis", "base_log_wis",
                                           "cov50", "cov80", "cov95"])
    figs = relwis.season_figures(old)
    assert figs.values["pf"] == pytest.approx(1.0)
    assert figs.detail["pf"]["log_rel"] is None
    assert figs.detail["pf"]["cov"] is None


def test_the_weekly_table_states_the_rule_and_what_the_us_row_is():
    df = pd.DataFrame([
        {"location": "Ohio", "fips": "39", "horizon": 1, "wis": 1.0,
         "base_wis": 2.0},
        {"location": "US", "fips": "US", "horizon": 1, "wis": 9.0,
         "base_wis": 10.0}])
    html = scoring.summary_table_html(df)
    assert scoring.CELL_RULE_NOTE in html
    assert usn.PF_US_NOTE in html
    # the Groundhog's US row is its own forecast: no such note
    assert usn.PF_US_NOTE not in scoring.summary_table_html(df, "analogue")


def test_the_earlier_rule_note_names_each_set_of_figures():
    note = scoring.earlier_rule_note(["the per-state table"],
                                     ["the pooled tiles", "the live scores",
                                      "the US figures"])
    assert ("stored scores, which used an earlier cell rule (settled truth "
            "and a forecast median both above 0): the per-state table. "
            "Scored under FluSight's rule: the pooled tiles, the live "
            "scores and the US figures.") in note


def test_a_sealed_record_page_says_which_figures_used_the_earlier_rule(
        world):                   # noqa: F811 (the fixture, imported above)
    """A sealed record's scores.json predates FluSight's rule: the page's
    pooled tiles and per-state table read it while the live scores are
    scored under the rule (playback._stats), so the page says which is
    which. A current file needs no such line."""
    from markupsafe import escape
    from test_retro_pf_name import SEASON as PN_SEASON, _page, _tree
    root = _tree(world["reseal"] / PN_SEASON)
    assert "earlier cell rule" not in _page(PN_SEASON)
    sf = root / "scores.json"
    pd.read_json(sf).drop(columns=[retro.SCORES_V_COLUMN]).to_json(sf)
    later = sf.stat().st_mtime + 5
    os.utime(sf, (later, later))
    note = scoring.earlier_rule_note(
        ["the pooled tiles", "the per-state table"], ["the live scores"])
    assert str(escape(note)) in _page(PN_SEASON)


# ------------------------------------------------ the replay's output floor

def _stub_pf_week(tmp_path, monkeypatch, collapsed):
    """run_week with stubbed engines; the vintage holds Ohio's last five
    weeks (1..5), which the floor's adaptive rate reads."""
    from app.core import data as _data
    from app.core import reclaim

    def fake_prepare(spec, wd):
        cells = [{"key": "c0", "dir": str(Path(wd) / "c0")}]
        (Path(wd) / "cells.json").write_text(json.dumps(cells))
        return cells

    class Runner:
        def __init__(self, wd, shard):
            self.wd, self.shard = Path(wd), list(shard)

        def poll(self):
            for c in self.shard:
                retro.mark_cell_done(self.wd, c["key"], "ok")
            return 0

        def kill(self):
            pass

    monkeypatch.setattr(retro.pf_engine, "prepare", fake_prepare)
    monkeypatch.setattr(retro.pf_engine, "collect",
                        lambda wd: {"Ohio": {k: list(v)
                                             for k, v in collapsed.items()}})
    monkeypatch.setattr(retro.oracle_mod, "apply_week",
                        lambda s, asof, wd, **kw: (s, {"applied": True}))
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {h: _flat(0.0)
                                               for h in hz.HORIZONS}})
    monkeypatch.setattr(retro, "_launch_runners",
                        lambda wd, shards, halt: [Runner(wd, s)
                                                  for s in shards])
    monkeypatch.setattr(retro, "_sleep", lambda s: None)
    monkeypatch.setattr(reclaim, "prune_week", lambda wd: 0)
    vf = tmp_path / "vintage.csv"
    days = pd.date_range(end=W1, periods=5, freq="7D")
    vf.write_text("date,location,value\n" + "".join(
        f"{d.date()},39,{i + 1}\n" for i, d in enumerate(days)))
    monkeypatch.setattr(_data, "vintage_path", lambda asof: vf)


def test_a_replayed_week_is_stored_through_the_output_floor(
        tmp_path, monkeypatch):
    collapsed = {hz.ORIGIN: [0.0] * 200,
                 **{h: [0.0] * 200 for h in hz.HORIZONS}}
    _stub_pf_week(tmp_path, monkeypatch, collapsed)
    root = tmp_path / SEASON
    retro.run_week(root, SEASON, W1, ["Ohio"], width=1)
    rec = retro.read_week_samples(root, W1)
    # the console's floor, with the vintage's recent weeks for the rate
    want = floor_samples(collapsed, "Ohio", W1, recent=[1.0, 2.0, 3.0,
                                                        4.0, 5.0])
    for h in hz.HORIZONS:
        assert rec["pf"]["Ohio"][h] == pytest.approx(want[h])
        assert np.quantile(rec["pf"]["Ohio"][h], 0.975) > 0   # no point mass
    # the analogue through floor_quantiles
    fq = floor_quantiles({h: _flat(0.0) for h in hz.HORIZONS})
    got = rec["analogue"]["Ohio"]["0"]
    assert {float(k): v for k, v in got.items()} == fq["0"]
    assert fq["0"][0.975] > 0


def test_the_floor_reads_the_same_recent_weeks_as_the_console(tmp_path):
    from app.core.floor import recent_observed
    vf = tmp_path / "v.csv"
    vf.write_text("date,location,value\n"
                  "2098-10-24,39,3\n2098-10-31,39,\n2098-11-07,39,5\n"
                  "2098-11-14,39,9\n2098-11-07,49,7\n")
    got = recent_observed(vf, ["Ohio", "Utah", "Nowhere"], W1)
    assert got == {"Ohio": [3.0, 5.0], "Utah": [7.0], "Nowhere": []}
    # the same-day rule leaves the as-of row out, as the engines do
    assert recent_observed(vf, ["Ohio"], W1, drop_same_day=True) == {
        "Ohio": [3.0]}


def test_the_run_record_says_the_floor_was_applied(tmp_path, monkeypatch):
    for fn in ("prepare", "collect"):
        monkeypatch.setattr(retro.pf_engine, fn, lambda *a, **k: 1 / 0)
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1])
    monkeypatch.setattr(retro.an_engine, "run",
                        lambda spec: {"Ohio": {h: _fan(20.0)
                                               for h in hz.HORIZONS}})
    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue")
    meta = retro.read_meta(root)
    assert meta["settings"]["output_floor"] == retro.FLOOR_APPLIED
    assert ("output floor", retro.FLOOR_APPLIED) in retro.settings_summary(
        meta)
    # a season stored before replays applied the floor says so, and a
    # resume of it names which weeks carry it
    meta["settings"].pop("output_floor")
    retro.write_meta(root, meta)
    assert ("output floor", retro.FLOOR_NOT_RECORDED) in \
        retro.settings_summary(retro.read_meta(root))
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue")
    assert (retro.read_meta(root)["settings"]["output_floor"]
            == retro.FLOOR_FROM_RESUME)


def test_the_site_cross_check_allows_the_earlier_rules_margin():
    from app.core import site_build as sb
    ok = sb.cross_check([{"season": "2024-25", "models": {"pf": {"rel": 0.798}}}],
                        {"2024-25": {"app_rel": 0.797}})
    assert ok[0]["ok"]
    bad = sb.cross_check([{"season": "2024-25", "models": {"pf": {"rel": 0.7995}}}],
                         {"2024-25": {"app_rel": 0.797}})
    assert not bad[0]["ok"]
