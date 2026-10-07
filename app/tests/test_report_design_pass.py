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
    assert "Reference date 2098-01-10 · data through Jan 3" in html
    d = report_v2.report_dates("2026-10-03")
    assert d["ref"] == "2026-10-10"
    assert d["line"] == "Reference date 2026-10-10 · data through Oct 3"


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
    assert "Gaps are shown" not in html          # the hatch is enough


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


def test_the_page_is_figures_without_prose(tmp_path):
    """Ely, 2026-10-07: the figures speak for themselves. No summary
    paragraph, no states-in-words list, no "?" explainers, no notes under
    the tables; the jump bar and the location picker stay."""
    html = _render(tmp_path)
    # no "?" buttons in the markup (the kit's inlined script names one)
    assert not re.search(r'aria-label="About [A-Za-z]', html)
    for gone in ('id="summary"', 'id="catlist"', 'class="rp-pooled"',
                 "Gaps are shown",
                 "flagged for a closer look", "is scored separately",
                 "Since the Oct 7", "A scored week is", "Wall time",
                 "Print or Save as PDF", "same weeks</span>"):
        assert gone not in html, gone
    nav = html[html.index('<nav class="rp-jump"'):].split("</nav>", 1)[0]
    for h in ("#map-anchor", "#us-feature", "#all-locations", "#accuracy",
              "#run"):
        assert f'href="{h}"' in nav, h
    assert '<option value="g-OH">Ohio</option>' in nav
    assert 'aria-label="Jump to location"' in nav


def test_detail_sections_sit_before_the_grid_with_both_members(tmp_path):
    html = _render(tmp_path)
    assert (html.index('id="map-anchor"') < html.index('id="st-OH"')
            < html.index('id="st-US"') < html.index('id="all-locations"'))
    sec = html[html.index('id="st-OH"'):].split("</section>", 1)[0]
    assert 'id="h-fan-OH">Weekly admissions</h3>' in sec
    assert "Next week (Oracle SIHRS)" in sec
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


def test_accuracy_card_folds_with_no_notes(tmp_path):
    html = _render(tmp_path)
    acc = html[html.index('id="accuracy"'):]
    assert '<h2 id="h-acc">Forecast accuracy</h2>' in acc
    assert '<details class="rp-acc" data-model="pf" data-pooled="0.500"' \
        in acc
    assert "Scored weeks" in acc and ">Cells<" not in acc
    assert "scored weeks</summary>" not in acc
    # notes an earlier run baked under its tables are dropped on rebuild
    baked = ("<div class='card' id='accuracy'><h2>Forecast accuracy, past "
             "weeks</h2><details class=\"rp-acc\"><summary>Oracle SIHRS "
             "pooled relWIS <b>0.812</b> over 1,234 scored weeks</summary>"
             "<table><tr><td>x</td></tr></table><p class=\"hint\">The US "
             "row is scored separately.</p><p class=\"hint\">A scored week "
             "is one forecast.</p></details></div>")
    out = report_v2._accuracy_card(baked, report_v2.kit_macros())
    assert "scored separately" not in out and "A scored week" not in out
    assert "over 1,234 scored weeks" not in out and "0.812" in out


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
    assert "Next week (Oracle SIHRS)" in sec
    assert "the model the map shows" not in html
