"""The honest US national aggregate on the retrospective season page.

The retro grid fits states only, so the national figure is CONSTRUCTED per
member from state forecasts with states treated as independent (PF: sample
draws summed by draw index; analogue: independent draws from each state's
quantile curve, summed). It is scored like every state, cached under the
season's stats validity key, and labelled as an aggregate wherever shown.
The per-state table is foldable, sortable and filterable.
"""
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro, scoring, us_national           # noqa: E402
from app.ui import server as srv                           # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL      # noqa: E402

SEASON = "2098-99"
W1 = "2098-01-03"
N2F = {"Ohio": "39", "Utah": "49"}


# ------------------------------------------------------------------ fixtures

def _tree(tmp_path, pf_a=(40.0, 60.0), pf_b=(60.0, 40.0)) -> Path:
    """One completed week, two states. The default PF draws index-sum to a
    degenerate 100, while a sorted (comonotone) sum would spread 80..120."""
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
    # scores.json newer than the samples: the stats validity key
    pd.DataFrame([{"model": "pf", "location": "Ohio", "fips": "39",
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
    """Index-aligned draws sum to (100, 100), exactly the US truth, so PF
    relWIS is 0; a rank-aligned sum would score positive WIS."""
    r = retro.national_aggregate(_tree(tmp_path))
    assert r is not None
    assert r["pf"] == 0.0
    assert r["cells"]["pf"] == 4                    # four horizons, one week


def test_both_national_scores_arrive_scored_like_states(
        tmp_path, _stub_scoring):
    r = retro.national_aggregate(_tree(tmp_path))
    for m in ("pf", "analogue"):
        assert m in r, m
        assert r[m] >= 0.0
        assert r["cells"][m] == 4
    # no blend: no national blend row either
    assert "ensemble" not in r and "ensemble" not in r["cells"]
    # the analogue national set carries spread: positive, finite relWIS
    assert r["analogue"] > 0.0
    assert r["pf"] < r["analogue"]
    assert r["weeks"] == 1
    assert r["seconds"] >= 0.0


def test_a_fitted_national_block_is_never_summed_into_the_aggregate(
        tmp_path, _stub_scoring):
    """A fitted `US` block in the week is never summed into the aggregate
    (it would double the national scale): both member loops skip it."""
    w = {"pf": .5, "analogue": .5}
    plain = retro.national_aggregate(_tree(tmp_path / "a"))
    root = _tree(tmp_path / "b")
    sp = root / "weeks" / W1 / "samples.json"
    d = json.loads(sp.read_text())
    # a fitted national block, on the same scale as the state sum (100)
    d["pf"]["US"] = {str(h): [100.0, 100.0] for h in range(5)}
    d["analogue"]["US"] = {str(h): {str(L): 100.0 for L in QL}
                           for h in range(1, 5)}
    sp.write_text(json.dumps(d))
    with_us = retro.national_aggregate(root)

    for r in (plain, with_us):
        r.pop("seconds", None)          # wall clock, not a result
    assert with_us == plain
    # index-aligned state sum is degenerate at the US truth (PF relWIS 0);
    # adding the national block would forecast 200 against 100
    assert with_us["pf"] == 0.0


def test_empty_season_returns_none(tmp_path, _stub_scoring):
    (tmp_path / SEASON / "weeks").mkdir(parents=True)
    assert retro.national_aggregate(tmp_path / SEASON) is None


# ------------------------------------------------------- cache and validity

def test_cached_under_the_stats_validity_key(tmp_path, _stub_scoring,
                                             monkeypatch):
    root = _tree(tmp_path)
    w = {"pf": .5, "analogue": .5}
    r1 = retro.national_aggregate(root)
    cf = root / "playback_cache" / "us_aggregate.json"
    assert cf.is_file()
    # a second call is served from the cache: truth loading would raise
    monkeypatch.setattr(scoring, "load_truth",
                        lambda: (_ for _ in ()).throw(AssertionError(
                            "cache miss recomputed")))
    assert retro.national_aggregate(root) == r1


def test_new_samples_invalidate_the_cache(tmp_path, _stub_scoring):
    root = _tree(tmp_path)
    w = {"pf": .5, "analogue": .5}
    r1 = retro.national_aggregate(root)
    sp = root / "weeks" / W1 / "samples.json"
    later = time.time() + 5
    os.utime(sp, (later, later))
    r2 = retro.national_aggregate(root)
    # deterministic recompute: the analogue draws are seeded per cell
    assert {m: r2[m] for m in ("pf", "analogue")} \
        == {m: r1[m] for m in ("pf", "analogue")}
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


#: A US figure travels with its provenance (app/core/us_national), so the
#: aggregate reaches the template through the resolver's serialisation.
US_ROW = us_national.UsNational(
    us_national.AGGREGATED,
    scores={"pf": 0.71, "analogue": 1.02, "ensemble": 0.66},
    cells={"pf": 4, "analogue": 4, "ensemble": 4},
    n_states=2).as_dict()


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
    assert "vincentized" not in body               # no blend since 2026-09-22
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
    for key in ("name", "pf", "analogue"):
        assert f'data-key="{key}"' in html, key
    assert 'data-key="ensemble"' not in html     # the retired blend: no column
    assert html.count('class="thsort"') == 3
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
