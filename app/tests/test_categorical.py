"""The FluSight rate-trend categories, computed the one way for every model
(app.core.categorical), and the retrospective map that now shows every
model a week stored through it."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import categorical as cat                        # noqa: E402
from app.core import horizons as hz                            # noqa: E402
from flubnf.quantiles import FLUSIGHT_QUANTILES as QL          # noqa: E402


# --------------------------------------------------------- the definition

def test_cutpoints_are_the_hubs_horizon_dependent_rates():
    """model-output/README.md of the FluSight hub: 0.3 and 1.7 per 100k
    one week ahead, then 0.5/3, 0.7/4, 1/5. In counts, for ten million
    people."""
    assert cat.cutpoints(10_000_000, 0) == (30.0, 170.0)
    assert cat.cutpoints(10_000_000, 1) == (50.0, 300.0)
    assert cat.cutpoints(10_000_000, 2) == (70.0, 400.0)
    assert cat.cutpoints(10_000_000, 3) == (100.0, 500.0)
    with pytest.raises(ValueError, match="hub horizon"):
        cat.cutpoints(10_000_000, 4)


def test_the_count_criterion_makes_small_changes_stable_everywhere():
    """A count change below 10 is stable whatever the rate. For a small
    jurisdiction the rate cut in counts is below 10, so 10 governs, and
    when even the large cut in counts is below 10 the increase band is
    empty: anything past stable reads large."""
    stable, large = cat.cutpoints(500_000, 0)      # 1.5 and 8.5 by rate
    assert (stable, large) == (10.0, 10.0)
    p = cat.probs_from_samples(np.full(200, 109.0), 100.0, 500_000, 0)
    assert p["stable"] == 1.0                          # +9: stable by count
    p = cat.probs_from_samples(np.full(200, 111.0), 100.0, 500_000, 0)
    assert p["large_increase"] == 1.0 and p["increase"] == 0.0
    # and a big jurisdiction keeps its increase band
    p = cat.probs_from_samples(np.full(200, 200.0), 100.0, 10_000_000, 0)
    assert p["increase"] == 1.0                        # +100: 30 <= 100 < 170


def test_samples_and_quantiles_are_one_computation():
    """The PF's draws and a 23-level grid reduced from them give the same
    categories, to the grid's resolution: one rule, two input shapes."""
    rng = np.random.default_rng(3)
    s = rng.gamma(9.0, 12.0, 20_000) + 40.0
    grid = {float(L): float(np.quantile(s, L)) for L in QL}
    for h in range(4):
        a = cat.probs_from_samples(s, 120.0, 4_000_000, h)
        b = cat.probs_from_quantiles(grid, 120.0, 4_000_000, h)
        assert abs(sum(a.values()) - 1.0) < 1e-9
        assert abs(sum(b.values()) - 1.0) < 1e-9
        for c in cat.CATS:
            assert abs(a[c] - b[c]) < 0.02, (h, c, a[c], b[c])


def test_the_legacy_entry_points_are_the_same_rule():
    from app.core.report import (categorical_probs,
                                 categorical_probs_from_quantiles)
    s = np.linspace(80.0, 220.0, 501)
    grid = {float(L): float(np.quantile(s, L)) for L in QL}
    assert categorical_probs(s, 100.0, 2_000_000, 1) == \
        cat.probs_from_samples(s, 100.0, 2_000_000, 1)
    assert categorical_probs_from_quantiles(grid, 100.0, 2_000_000, 2) == \
        cat.probs_from_quantiles(grid, 100.0, 2_000_000, 2)


# ------------------------------------------------ the retrospective map

SEASON, W1 = "2098-99", "2098-11-07"


def _q23(center):
    return {str(float(L)): center + 10.0 * (float(L) - 0.5) for L in QL}


def _root(tmp_path):
    """A one-week season root, stored form: pf draws with the anchor under
    "0" and four forecasts, the analogue's grids under "1".."4"."""
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    pf = {"Ohio": {"0": [100.0] * 5,
                   **{str(h): [100.0 + 40.0 * h + d for d in (-1, 0, 1)]
                      for h in range(1, 5)}},
          "Utah": {"0": [50.0] * 5,
                   **{str(h): [50.0 + d for d in (-1, 0, 1)]
                      for h in range(1, 5)}}}
    an = {"Ohio": {str(h): _q23(100.0 - 30.0 * h) for h in range(1, 5)},
          "Utah": {str(h): _q23(50.0) for h in range(1, 5)}}
    (wd / "samples.json").write_text(json.dumps(
        {"asof": W1, "pf": pf, "analogue": an}))
    return root


def test_every_stored_model_gets_map_cards_from_the_one_rule(tmp_path):
    import app.ui.server as srv
    root = _root(tmp_path)
    by_model = srv._week_map_cards_by_model(root, W1)
    assert set(by_model) == {"pf", "analogue"}
    # Ohio, 11.8 million people: one week ahead the PF says +40 (stable
    # cut 35, large 201: increase), the Groundhog says -30 (stable)
    pf_oh = by_model["pf"]["39"]["probs"]
    gh_oh = by_model["analogue"]["39"]["probs"]
    assert pf_oh["increase"] > 0.9
    assert gh_oh["stable"] > 0.9
    # Utah, 3.4 million: both say no change; stable by rate and by count.
    # The PF's three draws become a 23-level grid whose outermost levels
    # clamp the CDF at 1 and 99 percent, so the grid path reads 0.98.
    assert by_model["pf"]["49"]["probs"]["stable"] > 0.97
    assert by_model["analogue"]["49"]["probs"]["stable"] > 0.9
    # the hover carries the model's own numbers, escaped
    assert "1-wk median: 140" in by_model["pf"]["39"]["hover_html"]
    assert "1-wk median: 70" in by_model["analogue"]["39"]["hover_html"]
    # the one-model reader is the PF's, display order
    assert srv._week_map_cards(root, W1) == by_model["pf"]
    # cached per week, version 2 (the per-model shape)
    cf = root / "playback_cache" / "map_cards" / f"{W1}.json"
    assert json.loads(cf.read_text())["v"] == 2


def test_an_analogue_only_week_takes_its_baseline_from_the_vintage(
        tmp_path, monkeypatch):
    """A Groundhog-only replay stores no anchor draws; the baseline is the
    vintage's last reported value, and the map still renders."""
    import app.ui.server as srv
    root = tmp_path / SEASON
    wd = root / "weeks" / W1
    wd.mkdir(parents=True)
    (wd / "samples.json").write_text(json.dumps(
        {"asof": W1, "analogue": {"Ohio": {str(h): _q23(130.0)
                                           for h in range(1, 5)}}}))
    monkeypatch.setattr(srv, "_last_reported_before",
                        lambda wk, n2f: {"Ohio": 100.0})
    by_model = srv._week_map_cards_by_model(root, W1)
    assert set(by_model) == {"analogue"}
    assert by_model["analogue"]["39"]["probs"]["stable"] > 0.9   # +30 < 35


def test_the_mapswap_route_serves_every_model_and_keeps_the_old_shape(
        tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.ui.server as srv
    from app.core.usmap import state_paths
    root = _root(tmp_path)
    monkeypatch.setattr(srv, "_season_root", lambda s, a="": (root, False))
    r = TestClient(srv.app).get(f"/api/retro/{SEASON}/mapswap/{W1}")
    assert r.status_code == 200
    d = r.json()
    assert d["default"] == "pf"
    assert set(d["models"]) == {"pf", "analogue"}
    for m in d["models"].values():
        assert set(m["states"]) == set(state_paths())
    assert d["states"] == d["models"]["pf"]["states"]     # the old shape
    # the two models disagree on Ohio, so the swap changes the fill
    assert d["models"]["pf"]["states"]["39"]["f"] != \
        d["models"]["analogue"]["states"]["39"]["f"]


def test_the_season_page_offers_the_model_toggle_above_the_map(
        tmp_path, monkeypatch):
    """Two stored models: the home page's own control, under its own
    group id, sits above the retrospective map; the page script follows
    it across weeks."""
    import app.ui.server as srv
    from app.core import retro
    from fastapi.testclient import TestClient
    rr = tmp_path / "retro"
    root = _root(rr)
    monkeypatch.setattr(srv, "RETRO_ROOT", rr)
    monkeypatch.setattr(srv, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(srv, "RETRO_RESEAL", tmp_path / "noreseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1])
    # synthetic truth and baselines for both scoring surfaces, so the
    # season scores and the page renders its map rather than the
    # scoring-failed fragment that replaces it
    import pandas as pd
    from app.core import playback, scoring
    truth = {(f, pd.Timestamp(W1) + pd.Timedelta(days=7 * k)): base + k
             for f, base in (("39", 100.0), ("49", 50.0)) for k in range(-8, 8)}
    n2f = {"Ohio": "39", "Utah": "49"}
    for mod in (scoring, playback):
        monkeypatch.setattr(mod, "load_truth", lambda: (truth, n2f))
        monkeypatch.setattr(mod, "_baseline_cells",
                            lambda asof, fips_set, tr: {(f, asof, h): 2.0
                                                        for f in fips_set
                                                        for h in range(4)})
    monkeypatch.setattr(playback, "HUB", tmp_path / "hub")
    srv._invalidate_scans()
    html = TestClient(srv.app).get(f"/retro/{SEASON}").text
    assert 'data-fips="39"' in html                          # the map
    assert 'id="retro-model"' in html
    assert 'data-mmodel="pf" aria-pressed="true"' in html
    assert 'data-mmodel="analogue" aria-pressed="false"' in html
    assert "Groundhog categorical forecast" in html
    assert "#retro-model button[data-mmodel]" in html      # the follower
