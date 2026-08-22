"""The honest US national aggregate on the retrospective season page.

The retro grid fits states only, so the national figure is CONSTRUCTED:
each member aggregated from its state forecasts with states treated as
independent (PF by summing sample draws aligned by draw index; the
analogue by independent draws from each state's quantile curve, summed),
then the two national member quantile sets vincentized 50/50, the shipped
recipe. It is scored with the same relWIS machinery as every state, cached
under the season's stats validity key, and labeled as an aggregate
wherever it appears. Alongside it, the per-state table becomes a foldable,
sortable, filterable instrument.
"""
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro, scoring                        # noqa: E402
from app.ui import server as srv                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

SEASON = "2098-99"
W1 = "2098-01-03"
N2F = {"Ohio": "39", "Utah": "49"}


# ------------------------------------------------------------------ fixtures

def _tree(tmp_path, pf_a=(40.0, 60.0), pf_b=(60.0, 40.0)) -> Path:
    """One completed week, two states. The default PF draws are chosen so
    that the INDEX-ALIGNED sum is degenerate at 100 while a sorted
    (comonotone) sum would spread 80..120: the construction itself is what
    the relWIS then witnesses."""
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    pf = {"Ohio": {str(h): list(pf_a) for h in range(5)},
          "Utah": {str(h): list(pf_b) for h in range(5)}}
    an = {loc: {str(h): {str(L): 50.0 + (L - 0.5) * 20 for L in QL}
                for h in range(1, 5)}
          for loc in N2F}
    (wd / "samples.json").write_text(
        json.dumps({"asof": W1, "pf": pf, "analogue": an}))
    # scores.json present, newer than the samples: the stats validity key
    # the cache is bound to
    pd.DataFrame([{"model": "ensemble", "location": "Ohio", "fips": "39",
                   "asof": W1, "horizon": 0, "wis": 1.0, "base_wis": 2.0,
                   "rel": 0.5}]).to_json(root / "scores.json")
    return root


def _truth():
    t = {}
    for k in range(1, 5):
        d = pd.Timestamp(W1) + pd.Timedelta(days=7 * k)
        t[("39", d)] = 55.0
        t[("49", d)] = 45.0
        t[("US", d)] = 100.0          # the national truth row
    return t


@pytest.fixture
def _stub_scoring(monkeypatch):
    monkeypatch.setattr(scoring, "load_truth", lambda: (_truth(), dict(N2F)))
    monkeypatch.setattr(scoring, "_baseline_cells",
                        lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                    for f in fips_set
                                                    for h in range(4)})


# ------------------------------------------------- the construction itself

def test_pf_national_sums_draws_by_index_not_by_rank(tmp_path, _stub_scoring):
    """Ohio draws (40, 60) and Utah draws (60, 40) index-sum to (100, 100):
    a degenerate national forecast exactly on the US truth, so PF relWIS is
    0. A rank-aligned (comonotone) sum would spread 80..120 and score a
    strictly positive WIS; zero is the fingerprint of index alignment."""
    r = retro.national_aggregate(_tree(tmp_path),
                                 ensemble_weights={"pf": .5, "analogue": .5})
    assert r is not None
    assert r["pf"] == 0.0
    assert r["cells"]["pf"] == 4                    # four horizons, one week


def test_all_three_national_scores_arrive_scored_like_states(
        tmp_path, _stub_scoring):
    r = retro.national_aggregate(_tree(tmp_path),
                                 ensemble_weights={"pf": .5, "analogue": .5})
    for m in ("pf", "analogue", "ensemble"):
        assert m in r, m
        assert r[m] >= 0.0
        assert r["cells"][m] == 4
    # the analogue national set comes from two independent draws around a
    # symmetric curve summing to ~100: its relWIS is positive (it carries
    # spread) and finite
    assert r["analogue"] > 0.0
    # the ensemble blends a degenerate PF set with the analogue set 50/50,
    # so its intervals are half the analogue's: strictly between the two
    assert r["pf"] < r["ensemble"] < r["analogue"]
    assert r["weeks"] == 1
    assert r["seconds"] >= 0.0


def test_empty_season_returns_none(tmp_path, _stub_scoring):
    (tmp_path / SEASON / "weeks").mkdir(parents=True)
    assert retro.national_aggregate(tmp_path / SEASON) is None


# ------------------------------------------------------- cache and validity

def test_cached_under_the_stats_validity_key(tmp_path, _stub_scoring,
                                             monkeypatch):
    root = _tree(tmp_path)
    w = {"pf": .5, "analogue": .5}
    r1 = retro.national_aggregate(root, ensemble_weights=w)
    cf = root / "playback_cache" / "us_aggregate.json"
    assert cf.is_file()
    # a second call is served from the cache: truth loading would raise
    monkeypatch.setattr(scoring, "load_truth",
                        lambda: (_ for _ in ()).throw(AssertionError(
                            "cache miss recomputed")))
    assert retro.national_aggregate(root, ensemble_weights=w) == r1


def test_new_samples_invalidate_the_cache(tmp_path, _stub_scoring):
    root = _tree(tmp_path)
    w = {"pf": .5, "analogue": .5}
    r1 = retro.national_aggregate(root, ensemble_weights=w)
    sp = root / "weeks" / W1 / "samples.json"
    later = time.time() + 5
    os.utime(sp, (later, later))
    r2 = retro.national_aggregate(root, ensemble_weights=w)
    # deterministic recompute: the analogue draws are seeded per cell
    assert {m: r2[m] for m in ("pf", "analogue", "ensemble")} \
        == {m: r1[m] for m in ("pf", "analogue", "ensemble")}
    key = json.loads((root / "playback_cache"
                      / "us_aggregate.json").read_text())["key"]
    assert key["weeks"][W1] == int(later)


# --------------------------------------------- the page states it honestly

def _season_html(**kw):
    ctx = dict(active="Retrospective", season=SEASON,
               heads={"ensemble": 0.9},
               curve=[("2098-11-07", 0.95), ("2098-11-14", 0.9)],
               states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1,
                        "ensemble": 0.95}],
               weeks=["2098-11-07", "2098-11-14"], week="2098-11-14",
               map_html="<div id='usmap-wrap'></div>",
               official_catalog=[], n_weeks=2, score_error="")
    ctx.update(kw)
    return srv.templates.env.get_template("retro_season.html").render(**ctx)


US_ROW = {"pf": 0.71, "analogue": 1.02, "ensemble": 0.66,
          "cells": {"pf": 4, "analogue": 4, "ensemble": 4},
          "weeks": 2, "seconds": 61.0}


def test_us_row_and_tile_carry_the_honest_label():
    html = _season_html(us_row=US_ROW)
    # the distinct table row, in the shared exception coloring
    assert 'class="usagg"' in html
    assert html.count("US (aggregated)") >= 3       # tile, row, twice min
    # the tile
    assert "aggregated\n   from state forecasts, states treated as" \
        " independent" in html or \
        "aggregated from state forecasts" in html.replace("\n   ", " ")
    # the construction, stated in full under the table
    body = html.replace("\n", " ")
    assert "not a fitted national forecast" in body
    assert "states treated as independent" in body
    assert "vincentized 50/50" in body
    assert "aligned by draw index" in body


def test_without_a_us_row_nothing_national_renders():
    html = _season_html()
    assert "US (aggregated)" not in html
    assert 'class="usagg"' not in html


# ------------------------------- the per-state table is a real instrument

def test_per_state_table_folds_open_by_default_and_persists():
    html = _season_html()
    assert '<details class="ledgerfold" id="statefold" open>' in html
    assert "localStorage.getItem('statefold-open')==='0'" in html
    assert "localStorage.setItem('statefold-open'" in html


def test_sort_and_filter_controls_are_wired():
    html = _season_html()
    # aria-pressed header buttons for the state name and every member
    for key in ("name", "pf", "analogue", "ensemble"):
        assert f'data-key="{key}"' in html, key
    assert html.count('class="thsort"') == 4
    assert 'aria-pressed="false"' in html
    # rows carry the data the client sorts on
    assert 'data-name="Ohio"' in html
    assert 'data-pf="0.900000"' in html
    assert 'data-analogue="1.100000"' in html
    # the filter narrows by state name as you type
    assert 'id="sf-filter"' in html
    assert "addEventListener('input'" in html
    # n/a cells sort to the bottom in either direction
    assert "isNaN(v)?null:v" in html
