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
    # whole admissions, as the submitted CSV writes them
    assert p["models"]["pf"]["q"][0][2] == 25.0


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


def test_the_panel_reads_the_submitted_integers():
    """The CSV holds whole admissions (submit._hub_values: np.rint, half
    to even, then monotone); the panel and its flags read the same values.
    On the 2026-10-03 dry run Rhode Island's Oracle h3 median was 2.89 and
    its latest count 3: the file says 3, so nothing falls."""
    import numpy as np
    from app.core.submit import _hub_values
    raw = [0.4, 1.5, 2.5, 2.89, 7.49]
    assert [G._whole(v) for v in raw] == [float(v) for v in
                                          _hub_values(raw)]
    q = {str(h): {0.025: 0.4, 0.25: 1.5, 0.5: 2.89, 0.75: 2.5, 0.975: 7.49}
         for h in range(4)}
    f = G.model_fan(q, ["t"] * 4)
    assert f["q"][3] == [0.0, 2.0, 3.0, 3.0, 7.0]      # monotone after rint
    p = {"observed": [[ASOF, 3.0]], "models": {"pf": f}}
    assert G.flags(p) == []
    assert np.rint(2.5) == G._whole(2.5) == 2.0


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


def test_a_panel_is_plain_one_band_per_model():
    """One shaded band per model (the 95% interval), last season dashed,
    the latest count in full with its unit, the flags beside it; no
    off-scale note, and a name is escaped."""
    p = {"key": "XX", "name": "<b>A&B</b>", "observed": [[ASOF, 2515.0]],
         "last_season": [[ASOF, 2000.0], ["2098-01-10", 2100.0]],
         "models": {"analogue": {"times": ["2098-01-10", "2098-01-17",
                                           "2098-01-24", "2098-01-31"],
                                 "q": [[1, 9, 2000, 11, 90000]] * 4}}}
    html = G.grid_html({"panels": [p], "asof": ASOF}, COLORS)
    assert "&lt;b&gt;A&amp;B&lt;/b&gt;" in html and "<b>A&B</b>" not in html
    assert "latest: 2,515 admissions" in html
    assert html.count("<polygon") == 1               # the 95% band alone
    assert "off scale" not in html
    assert "bands: 95% interval" in html and "50%" not in html
    assert "stroke-dasharray:4 3" in G.grid_css()    # last season, dashed
    # the flags sit in their own group at the right of the caption
    p["observed"] = [[ASOF, 5000.0]]
    assert '<span class="g-flags"><span class="g-flag g-flag--warn"' in G.grid_html(
        {"panels": [p], "asof": ASOF}, COLORS)
    assert "latest: 1 admission<" in G._latest({"observed": [[ASOF, 1.0]]})


def test_the_us_panel_sits_large_under_the_map(tmp_path):
    g = _grid()
    side = G.us_feature_html(g, COLORS)
    assert 'class="rp-usfeature"' in side and "United States" in side
    assert "Oracle SIHRS" in side and "last season" in side
    assert G.us_feature_html(_grid(("Ohio",)), COLORS) == ""
    b = {"version": report_v2.BUNDLE_VERSION, "asof": ASOF, "cards": {},
         "details": {}, "national": {}, "grid": g}
    html = report_v2.render_bundle(b, tmp_path / "r.html").read_text(
        encoding="utf-8")
    card = html.split('id="map-anchor"', 1)[1].split('id="all-locations"')[0]
    assert 'class="rp-usfeature"' in card and "rp-mapsplit" not in card
    # under the map and its legends, inside the map's card
    assert card.index('class="rp-legends"') < card.index("rp-usfeature")


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


def test_print_keeps_the_key_and_explains_the_flags():
    """Browsers print without background colours by default: the legend
    swatches ask to be printed exactly. Each page head says what the flag
    words mean (a paper copy has no hover)."""
    css = G.grid_css()
    i_rule = css[css.index(".g-key i{"):].split("}", 1)[0]
    assert "print-color-adjust:exact" in i_rule
    assert "-webkit-print-color-adjust:exact" in i_rule
    html = G.grid_html(_grid(), COLORS)
    key = G.flag_key("Jan 31").replace("'", "&#x27;")   # the last target
    assert html.count(key) == 1                           # one page


def test_bands_first_then_medians_and_the_zero_line_draws_whole():
    """Both 95% bands go down before either median, so no band tints the
    other model's line; the clip reaches a little below zero, so a 0
    median or count is not cut in half; a half-way tick reads 7.5."""
    svg, _ = G.panel_svg(_grid()["panels"][2], 0, COLORS)
    polys = [m.start() for m in re.finditer("<polygon", svg)]
    meds = [m.start() for m in re.finditer('stroke-width="1.8"', svg)]
    assert len(polys) == 2 and len(meds) == 2 and max(polys) < min(meds)
    h = float(re.search(r'clipPath id="gclip0"><rect [^>]*height="([\d.]+)"',
                        svg).group(1))
    assert h > G.H - G.MT - G.MB
    assert G._num(7.5) == "7.5" and G._num(15.0) == "15"
    assert G._num(2500.0) == "2.5k"


def test_the_us_panel_says_what_the_oracle_sihrs_us_row_is():
    g = _grid()
    for step, words in (("stepped", "uses the same Oracle step as the states"),
                        ("filter", "Liu-West filter alone")):
        g["us_step"] = step
        assert words in G.us_feature_html(g, COLORS)
    g["us_step"] = None
    assert "g-usnote" not in G.us_feature_html(g, COLORS)


# ------------------------------------------------ design pass (2026-10-05)

def test_panels_wear_the_member_tokens_and_the_groundhog_band_is_an_outline():
    """Member colours come from the page's --model-* tokens (a light card
    takes a darker Groundhog gold); the Groundhog's 95% band is an outline
    over a faint fill, the Oracle SIHRS band a fill, so an overlap never
    turns grey."""
    svg, _ = G.panel_svg(_grid()["panels"][2], 0, COLORS)
    assert "fill:var(--model-pf, #1979FF)" in svg
    assert "stroke:var(--model-analogue, #FFC72C)" in svg
    assert 'class="g-band g-band-analogue"' in svg
    assert 'class="g-band g-band-pf"' in svg
    assert 'fill="#FFC72C"' not in svg and 'stroke="#1979FF"' not in svg
    css = G.grid_css()
    assert ".g-band-analogue{fill-opacity:.07;stroke-width:1.1" in css
    assert ".g-band-pf{fill-opacity:var(--rp-band-a" in css


def test_flags_falls_in_the_warning_colour_disagree_in_red():
    p = {"key": "XX", "name": "X", "observed": [[ASOF, 100.0]], "models": {
        "pf": {"times": ["2098-01-31"] * 4, "q": [[10, 20, 30, 40, 50]] * 4},
        "analogue": {"times": ["2098-01-31"] * 4,
                     "q": [[300, 400, 500, 600, 900]] * 4}}}
    html = G.grid_html({"panels": [p], "asof": ASOF}, COLORS)
    assert 'g-flag g-flag--warn" title="4-week-ahead median below' in html
    assert 'g-flag g-flag--bad" title="by Jan 31 one model' in html
    assert ".g-flag--warn{color:var(--warn)}" in G.grid_css()
    # no reported data says so; data without a fan is "no forecast"
    assert "no data</span>" in G._flag_spans({"observed": [], "models": {}})
    assert "no forecast</span>" in G._flag_spans(
        {"observed": [[ASOF, 3.0]], "models": {}})


def test_a_clipped_band_shows_where_it_continues():
    p = {"key": "XX", "name": "X", "observed": [[ASOF, 20.0]],
         "models": {"analogue": {"times": ["2098-01-10", "2098-01-17",
                                           "2098-01-24", "2098-01-31"],
                                 "q": [[1, 9, 20, 30, 900]] * 4}}}
    svg, clipped = G.panel_svg(p, 0, COLORS)
    assert clipped and svg.count('class="g-cont"') == 4
    assert "continues above the scale (to 900)" in svg


def test_the_us_feature_is_wide_and_short_with_panel_sized_text():
    side = G.us_feature_html(_grid(), COLORS)
    assert f'viewBox="0 0 {G.FEATURE_W} {G.FEATURE_H}"' in side
    assert f'font-size="{G.FEATURE_FS}"' in side
    assert G.FEATURE_W / G.FEATURE_H > 3


def test_pages_name_the_reference_date_and_number_themselves():
    html = G.grid_html(_grid(), COLORS)
    assert "Reference date 2098-01-10 &middot; locations 1 to 3 of 3" in html
    assert ("FluBNF &middot; reference date 2098-01-10 &middot; All "
            "locations, page 1 of 1") in html
    assert "Every location&#x27;s forecast" in html or \
        "Every location's forecast" in html
    # a link mark per panel, and a spoken summary with each model's numbers
    assert 'class="g-anchor" href="#g-OH"' in html
    assert "Oracle SIHRS median for Jan 31" in html
