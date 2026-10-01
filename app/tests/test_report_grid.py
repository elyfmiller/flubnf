"""The weekly report's "All locations" pages (app/core/report_grid.py):
every location's forecast at a glance, both models in each panel, last
season's counts over the same weeks, 3 across and 5 down when printed."""
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import report_grid as G                         # noqa: E402
from app.core import report_v2                                 # noqa: E402

ASOF = "2098-01-03"
COLORS = {"pf": "#1979FF", "analogue": "#FFC72C"}


def _fan(med, spread=0.2, growth=1.1):
    """horizon -> {level: value}, the members' shape (float level keys)."""
    out = {}
    for h in range(4):
        m = med * growth ** (h + 1)
        out[str(h)] = {L: m * (1 + spread * z) for L, z in
                       ((0.025, -1.9), (0.25, -0.7), (0.5, 0),
                        (0.75, 0.7), (0.975, 1.9))}
    return out


def _weeks(end: str, n: int, start_value=10.0):
    e = date.fromisoformat(end)
    return [((e - timedelta(days=7 * (n - 1 - i))).isoformat(),
             start_value + i) for i in range(n)]


def _grid(names=("Ohio", "US", "Alabama"), **kw):
    keys = {"Ohio": "OH", "US": "US", "Alabama": "AL"}
    titles = {"US": "United States"}
    obs = {n: _weeks(ASOF, 14) for n in names}
    hist = {n: _weeks(ASOF, 80, 1.0) for n in names}
    q = kw.get("model_q") or {"pf": {n: _fan(23.0) for n in names},
                               "analogue": {n: _fan(24.0, 0.5)
                                            for n in names}}
    return G.grid_data(ASOF, list(names), keys, titles, obs, q, hist)


def test_the_grid_holds_each_location_us_first_then_by_name():
    g = _grid()
    assert [p["key"] for p in g["panels"]] == ["US", "AL", "OH"]
    assert g["panels"][0]["name"] == "United States"
    assert g["times"] == ["2098-01-10", "2098-01-17", "2098-01-24",
                          "2098-01-31"]
    p = g["panels"][2]
    # the last OBS_WEEKS observed weeks, ending at the as-of
    assert len(p["observed"]) == G.OBS_WEEKS
    assert p["observed"][-1][0] == ASOF
    # both models, each four horizons of [2.5, 25, 50, 75, 97.5]
    assert set(p["models"]) == {"pf", "analogue"}
    for f in p["models"].values():
        assert f["times"] == g["times"] and len(f["q"]) == 4
        assert all(len(r) == 5 and r == sorted(r) for r in f["q"])
    assert p["models"]["pf"]["q"][0][2] == round(23.0 * 1.1, 2)


def test_last_season_is_the_same_weeks_a_year_earlier():
    """52 weeks back (the same weekday), drawn on this season's dates."""
    g = _grid()
    assert g["last_season_label"] == "2096-97"
    ls = g["panels"][2]["last_season"]
    first = g["panels"][2]["observed"][0][0]
    assert ls[0][0] == first and ls[-1][0] == g["times"][-1]
    # each value is the count 364 days before its plotted date
    hist = dict(_weeks(ASOF, 80, 1.0))
    for d, v in ls:
        back = (date.fromisoformat(d) - timedelta(days=364)).isoformat()
        assert hist[back] == v
    assert G.season_label(date(2026, 9, 26)) == "2026-27"
    assert G.season_label(date(2027, 3, 6)) == "2026-27"
    assert G.season_label(date(2025, 10, 4)) == "2025-26"


def test_a_model_without_four_horizons_is_left_out():
    q = {"pf": {"Ohio": {"0": {0.5: 3.0}}},          # one horizon only
         "analogue": {"Ohio": _fan(20.0)}}
    p = _grid(("Ohio",), model_q=q)["panels"][0]
    assert set(p["models"]) == {"analogue"}
    none = _grid(("Ohio",), model_q={"pf": {}, "analogue": {}})["panels"][0]
    assert none["models"] == {}
    assert "no forecast" in G.grid_html({"panels": [none], "asof": ASOF},
                                        COLORS)


def test_flags_name_a_falling_median_and_models_that_disagree():
    obs = [[ASOF, 100.0]]
    ok = {"observed": obs, "models": {
        "pf": {"times": [], "q": [[80, 95, 110, 125, 150]] * 4},
        "analogue": {"times": [], "q": [[60, 90, 115, 140, 200]] * 4}}}
    assert G.flags(ok) == []
    falls = json.loads(json.dumps(ok))
    falls["models"]["pf"]["q"][3] = [50, 70, 80, 90, 120]
    assert [w for w, _ in G.flags(falls)] == ["falls"]
    assert "Oracle SIHRS" in G.flags(falls)[0][1]
    apart = json.loads(json.dumps(ok))
    apart["models"]["analogue"]["q"][3] = [300, 400, 500, 600, 900]
    assert [w for w, _ in G.flags(apart)] == ["disagree"]
    # one model alone cannot disagree; no counts, nothing falls
    assert G.flags({"observed": [], "models": {
        "pf": {"times": [], "q": [[1, 2, 3, 4, 5]] * 4}}}) == []


def test_the_pages_are_fifteen_panels_three_across():
    """53 locations: four pages of 15, 15, 15 and 8, each headed with the
    week, its range and the legend; print CSS makes each a Letter page."""
    names = [f"Place {i:02d}" for i in range(52)] + ["US"]
    keys = {n: ("US" if n == "US" else f"P{i:02d}")
            for i, n in enumerate(names)}
    q = {"pf": {n: _fan(20.0) for n in names},
         "analogue": {n: _fan(20.0, 0.4) for n in names}}
    obs = {n: _weeks(ASOF, 12) for n in names}
    g = G.grid_data(ASOF, names, keys, {"US": "United States"}, obs, q, {})
    html = G.grid_html(g, COLORS, details={"P00", "US"})
    pages = html.split('<div class="gpage">')[1:]
    assert [p.count('<figure class="gpanel"') for p in pages] == \
        [15, 15, 15, 8]
    assert "locations 1 to 15 of 53" in pages[0]
    assert "locations 46 to 53 of 53" in pages[3]
    for p in pages:
        assert "Oracle SIHRS" in p and "Groundhog" in p and "last season" in p
    # a panel title opens the location's detail section where there is one
    assert "showState('st-P00')" in html and "showState('st-US')" in html
    assert "showState('st-P01')" not in html
    # every clip path is the panel's own
    ids = re.findall(r'clipPath id="(gclip\d+)"', html)
    assert len(ids) == 53 == len(set(ids))
    css = G.grid_css()
    assert "@page{size:letter portrait" in css
    assert "repeat(3,minmax(0,1fr))" in css and ".gpage{break-after:page" in css


def test_a_name_is_escaped_and_the_scale_says_when_it_clips():
    p = {"key": "XX", "name": "<b>A&B</b>", "observed": [[ASOF, 10.0]],
         "last_season": [],
         "models": {"analogue": {"times": ["2098-01-10"] * 4,
                                 "q": [[1, 9, 10, 11, 900]] * 4}}}
    html = G.grid_html({"panels": [p], "asof": ASOF}, COLORS)
    assert "&lt;b&gt;A&amp;B&lt;/b&gt;" in html and "<b>A&B</b>" not in html
    assert "95% off scale" in html
    p["models"]["analogue"]["q"] = [[8, 9, 10, 11, 12]] * 4
    assert "95% off scale" not in G.grid_html({"panels": [p], "asof": ASOF},
                                              COLORS)


def test_the_report_carries_the_pages_and_an_older_bundle_does_not(tmp_path):
    g = _grid()
    b = {"version": report_v2.BUNDLE_VERSION, "asof": ASOF, "cards": {},
         "details": {}, "national": {}, "grid": g}
    html = report_v2.render_bundle(b, tmp_path / "r.html").read_text(
        encoding="utf-8")
    assert 'id="all-locations"' in html and "All locations" in html
    assert "@page{size:letter portrait" in html
    # the pages sit under the map, before the detail sections
    assert html.index('id="map-anchor"') < html.index('id="all-locations"')
    b.pop("grid")
    b["version"] = 7
    old = report_v2.render_bundle(b, tmp_path / "o.html").read_text(
        encoding="utf-8")
    assert 'id="all-locations"' not in old and "@page" not in old


def test_the_weekly_run_writes_the_grid(tmp_path, monkeypatch):
    """Through the real build path: one panel per run location, both
    models where they ran, last season from the newest vintage."""
    from app.tests.test_report_bundle import _synth_run
    from app.ui import state
    vint = tmp_path / "vintage.csv"
    rows = ["date,location,value"] + [
        f"{d},{f},{v}" for f in ("39", "US")
        for d, v in _weeks("2097-02-07", 60, 5.0)]
    vint.write_text("\n".join(rows) + "\n")
    monkeypatch.setattr(state.data_mod, "vintages", lambda: ["2097-12-27"])
    monkeypatch.setattr(state.data_mod, "vintage_path", lambda v: vint)
    _synth_run(tmp_path / "w")
    bundle = json.loads((tmp_path / "w" / report_v2.BUNDLE_NAME).read_text(
        encoding="utf-8"))
    g = bundle["grid"]
    assert [p["key"] for p in g["panels"]] == ["US", "OH"]
    assert g["asof"] == "2098-01-03"
    for p in g["panels"]:
        assert set(p["models"]) == {"pf"}          # the PF-only fixture
        assert p["last_season"], p["key"]
        assert all(d >= p["observed"][0][0] for d, _ in p["last_season"])
    html = (tmp_path / "w" / "report.html").read_text(encoding="utf-8")
    assert 'id="all-locations"' in html
