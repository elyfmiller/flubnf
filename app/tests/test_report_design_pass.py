"""The weekly report's themes, text and spacing pass (2026-10-05): member
colour tokens, the no-data hatch, the color-blind safe switch, forced
colours, the summary line, the jump bar, the category list, keyboard map
states, the detail sections (both members, the numbers, before the grid),
the folded accuracy tables and the run card."""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import report_v2, scoring, usmap               # noqa: E402
from app.tests.test_report_grid import ASOF, _grid           # noqa: E402

OH_Q = {t: {str(lv): 20.0 + 10 * lv for lv in report_v2.FAN_LEVELS}
        for t in ("2098-01-10", "2098-01-17", "2098-01-24", "2098-01-31")}


def _bundle(**kw):
    g = _grid()
    df = pd.DataFrame([
        {"location": "Ohio", "fips": "39", "horizon": 1, "wis": 1.0,
         "base_wis": 2.0},
        {"location": "US", "fips": "US", "horizon": 1, "wis": 9.0,
         "base_wis": 10.0}])
    acc = ("<div class='card' id='accuracy'><h2>Forecast accuracy, past "
           "weeks</h2>" + scoring.summary_table_html(df, model="pf")
           + "</div>")
    b = {"version": report_v2.BUNDLE_VERSION, "asof": ASOF,
         "cards_model": "pf",
         "cards": {"OH": {"fips": "39", "name": "Ohio", "abbr": "OH",
                          "probs": {"increase": .7, "stable": .3},
                          "hover_html": "<b>Ohio</b>"}},
         "fitted_fips": ["39", "56"], "gap_fips": ["56"],
         "details": {"OH": {"name": "Ohio", "model": "pf",
                            "fan": {"observed_times": ["2098-01-03"],
                                    "observed": [23.0],
                                    "forecast_times": list(OH_Q),
                                    "quantiles": OH_Q},
                            "cat_probs": {"increase": .7, "stable": .3},
                            "table_rows": [["2097-12-27", 1234.0]]}},
         "national": {"summary_html": acc}, "grid": g,
         "elapsed_s": 1834.0,
         "settings_html": ('<div class="hint runsettings"><strong>Run '
                           'settings</strong><dl class="kv"><dt>engine</dt>'
                           '<dd>pf</dd><dt>bngsim</dt><dd>not installed</dd>'
                           '</dl></div>')}
    b.update(kw)
    return b


def _render(tmp_path, **kw):
    return report_v2.render_bundle(_bundle(**kw), tmp_path / "r.html") \
        .read_text(encoding="utf-8")


def test_title_and_page_name_the_reference_date(tmp_path):
    html = _render(tmp_path)
    assert "<title>FluBNF weekly report, reference date 2098-01-10</title>" \
        in html
    assert ("Data through Fri Jan 3, 2098 · forecasts for Jan 10 to "
            "Jan 31 (FluSight reference date 2098-01-10)") in html
    d = report_v2.report_dates("2026-10-03")
    assert d["ref"] == "2026-10-10"
    assert d["line"].startswith("Data through Sat Oct 3, 2026")
    assert "forecasts for Oct 10 to Oct 31" in d["line"]


def test_member_tokens_bands_and_no_data_per_card(tmp_path):
    html = _render(tmp_path)
    css = report_v2._report_tokens_css()
    assert f"--model-analogue:{report_v2.ANALOGUE_ON_LIGHT}" in css
    assert "--model-analogue:#FFC72C" in css.split('[data-theme="dim"]')[1]
    assert "--map-nodata:#7D83A3" in css and "--map-nodata:#8E89A6" in css
    # the report's tokens follow nau.css's blocks, and print still wins
    assert html.index(css) > html.index(report_v2.theme_token_css())
    assert html.rindex("@media print") > html.index(css)


def test_reporting_gap_is_hatched_and_reads_no_data(tmp_path):
    html = _render(tmp_path)
    assert f'<pattern id="{usmap.GAP_PATTERN_ID}"' in html
    m = re.search(r'<path [^>]*data-fips="56"[^>]*>', html)
    assert 'fill="url(#nodata-hatch)"' in m.group(0)
    assert 'aria-label="Wyoming: no data"' in m.group(0)
    assert f"--sw:{usmap.GAP_SWATCH}" in html
    assert ("Nothing was reported for these states this week. Gaps are "
            "shown, never filled in.") in html


def test_map_states_take_the_keyboard(tmp_path):
    html = _render(tmp_path)
    m = re.search(r'<path [^>]*data-fips="39"[^>]*>', html)
    assert 'role="button" tabindex="0"' in m.group(0)
    assert 'aria-label="Ohio: increase 70%"' in m.group(0)
    assert "ev.key !== 'Enter' && ev.key !== ' '" in html
    pay = usmap.state_swap_payload(
        {"39": {"probs": {"stable": 1.0}, "name": "Ohio"}})
    assert pay["39"]["a"] == "Ohio: stable 100%"


def test_vision_switch_forced_colors_and_print_palette(tmp_path):
    html = _render(tmp_path)
    assert 'id="visionbtn" class="rp-btn" aria-pressed="false"' in html
    assert "de.setAttribute('data-vision','cvd')" in html
    fc = html[html.index("@media (forced-colors:active){\n  .uk-seg"):]
    assert "forced-color-adjust:none;background:Highlight;" in fc
    assert "color:HighlightText" in fc
    pr = report_v2.page_style()
    pr = pr[pr.rindex("@media print{"):]
    assert "--cat-large-increase:#D7191C" in pr       # the cvd scale
    assert "addEventListener('beforeprint'" in html
    assert "de.setAttribute('data-vision', 'cvd')" in html


def test_summary_jump_bar_and_category_list(tmp_path):
    html = _render(tmp_path)
    s = html[html.index('id="summary"'):].split("</p>", 1)[0]
    assert "United States: <b>23</b> admissions in the week ending Jan 3" \
        in s
    assert "Oracle SIHRS median for Jan 31" in s
    assert "1 state leans toward an increase" in s
    nav = html[html.index('<nav class="rp-jump"'):].split("</nav>", 1)[0]
    for h in ("#map-anchor", "#us-feature", "#all-locations", "#accuracy",
              "#run"):
        assert f'href="{h}"' in nav, h
    assert '<option value="g-OH">Ohio</option>' in nav
    cl = html[html.index('id="catlist"'):].split("</details>", 1)[0]
    assert "Increase</dt><dd>Ohio</dd>" in cl
    assert "No data</dt><dd>Wyoming</dd>" in cl


def test_detail_sections_sit_before_the_grid_with_both_members(tmp_path):
    html = _render(tmp_path)
    assert (html.index('id="map-anchor"') < html.index('id="st-OH"')
            < html.index('id="st-US"') < html.index('id="all-locations"'))
    sec = html[html.index('id="st-OH"'):].split("</section>", 1)[0]
    assert 'id="h-fan-OH">Weekly admissions</h3>' in sec
    assert "Rate-change outlook, next week" in sec
    assert "<td>Dec 27</td><td class=\"num\">1,234</td>" in sec
    # the forecast numbers: both members, four target weeks
    num = sec[sec.index('id="num-OH"'):]
    assert "Oracle SIHRS</th>" in num and "Groundhog</th>" in num
    assert num.count('<th scope="row">') == 4
    assert '"scrollZoom": false' in html
    # the fan carries the Groundhog from the grid, one legend row
    fig = report_v2.fan_figure_from_quantiles(
        ["2098-01-03"], [23.0], list(OH_Q), OH_Q,
        others={"analogue": OH_Q})
    names = [t.name for t in fig.data if t.showlegend is not False]
    assert names == ["Groundhog", "Oracle SIHRS", "observed"]
    assert fig.layout.yaxis.rangemode == "tozero"
    pf_med = next(t for t in fig.data if t.name == "Oracle SIHRS")
    assert pf_med.x[0] == "2098-01-03" and pf_med.y[0] == 23.0


def test_accuracy_card_folds_and_pooled_figures_show_by_the_map(tmp_path):
    html = _render(tmp_path)
    acc = html[html.index('id="accuracy"'):]
    assert "Forecast accuracy, past weeks" in acc
    assert "relWIS: relative WIS, below 1 beats the FluSight baseline" in acc
    assert '<details class="rp-acc" data-model="pf" data-pooled="0.500"' \
        in acc
    assert "Scored weeks" in acc and ">Cells<" not in acc
    head = html[html.index('id="map-anchor"'):].split("</div>", 1)[0]
    assert 'class="rp-pooled"' in head and "0.500" in head
    assert "openAccuracy()" in head
    # an older report's tables still give the figure
    old = ("<div class='card'><h2>forecast accuracy (retrospective)</h2>"
           "<table><thead><tr><th>Location</th><th class=\"num\">Oracle "
           "SIHRS relWIS</th><th class=\"num\">Cells</th></tr></thead><tbody>"
           "<tr class=\"total\"><td>All locations</td><td class=\"num ok\">"
           "0.812</td><td class=\"num hint\">40</td></tr></tbody></table>"
           "</div>")
    assert report_v2._pooled_figures(old) == [("Oracle SIHRS", 0.812, 40)]


def test_run_card_words_its_time_and_hides_missing_engines(tmp_path):
    html = _render(tmp_path)
    run = html[html.index('id="run"'):]
    assert '<span class="uk-stat-v" id="runtime">30 min 34 s</span>' in run
    assert '<span class="uk-fold-sum">Run details</span>' in run
    assert "<dt>engine</dt>" in run and "not installed" not in run
    assert report_v2._run_time(3725) == "1 h 2 min 5 s"


def test_an_older_bundle_still_renders_one_member(tmp_path):
    b = _bundle(version=7)
    b.pop("grid")
    html = report_v2.render_bundle(b, tmp_path / "o.html").read_text(
        encoding="utf-8")
    sec = html[html.index('id="st-OH"'):].split("</section>", 1)[0]
    assert "Oracle SIHRS</th>" in sec and "Groundhog</th>" not in sec
    assert 'id="all-locations"' not in html


def test_summary_counts_states_only(tmp_path):
    # the nation and Puerto Rico lean too, but they are not states
    up = {"increase": .8, "stable": .2}
    cards = {"OH": {"fips": "39", "name": "Ohio", "abbr": "OH",
                    "probs": up, "hover_html": "<b>Ohio</b>"},
             "US": {"fips": "US", "name": "United States", "abbr": "US",
                    "probs": up, "hover_html": "<b>US</b>"},
             "PR": {"fips": "72", "name": "Puerto Rico", "abbr": "PR",
                    "probs": up, "hover_html": "<b>PR</b>"}}
    html = _render(tmp_path, cards=cards)
    s = html[html.index('id="summary"'):].split("</p>", 1)[0]
    assert "1 state leans toward an increase" in s


def test_small_count_fans_never_print_si_prefixes():
    t = ["2098-01-10", "2098-01-17"]
    small = {x: {str(lv): 2.0 * lv for lv in report_v2.FAN_LEVELS} for x in t}
    fig = report_v2.fan_figure_from_quantiles(["2098-01-03"], [1.0], t, small)
    assert fig.layout.yaxis.tickformat == ",~g"
    big = {x: {str(lv): 3000.0 * lv for lv in report_v2.FAN_LEVELS} for x in t}
    fig = report_v2.fan_figure_from_quantiles(["2098-01-03"], [2500.0], t, big)
    assert fig.layout.yaxis.tickformat == "~s"


def test_rate_change_bar_names_its_member(tmp_path):
    html = _render(tmp_path)
    sec = html[html.index('id="st-OH"'):].split("</section>", 1)[0]
    assert "Rate-change outlook, next week (Oracle SIHRS)" in sec
    assert "the model the map shows" not in html
