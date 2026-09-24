"""Date-axis ticks land on the data's Saturdays (app/ui/static/charts.js).

Every FluSight point is an MMWR week-ending Saturday; Plotly's automatic
weekly ticks land on Sundays, and tick0 alone drops it to daily ticks. The
one helper, FluCharts, sets tick0 on a Saturday, a whole-week dtick chosen
from the visible span and width, and a date tickformat, and every date
chart (console pages, the Retrospective player, both reports) draws
through it. The helper's output is asserted by running charts.js in node
(skipped where node is absent); the wiring is asserted as text."""
import json
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "ui" / "static"
TEMPLATES = ROOT / "app" / "ui" / "templates"
CHARTS = STATIC / "charts.js"
WEEK_MS = 7 * 864e5
NODE = shutil.which("node")


def _node(expr: str):
    """Evaluate `expr` with F = charts.js's exports; returns parsed JSON."""
    script = (f"const F = require({json.dumps(str(CHARTS))});"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run([NODE, "-e", script], capture_output=True,
                         text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _ticks(policy, x0: str, x1: str) -> list:
    """The tick dates Plotly draws for a linear date policy on [x0, x1]."""
    t0 = date.fromisoformat(policy["tick0"])
    step = int(round(policy["dtick"] / 864e5))
    lo, hi = date.fromisoformat(x0), date.fromisoformat(x1)
    k = -(-((lo - t0).days) // step)          # ceil
    out, d = [], t0 + timedelta(days=k * step)
    while d <= hi:
        out.append(d)
        d += timedelta(days=step)
    return out


needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

# (x0, x1): a forecast fan across the 2025-26 year boundary, a whole
# season, the full hub archive, and a view across 2026 MMWR week 53
# (the week ending Saturday 2027-01-02)
SPANS = [("2025-10-18", "2026-02-07"), ("2025-08-02", "2026-07-25"),
         ("2023-09-23", "2026-07-04"), ("2026-12-05", "2027-01-16")]
WIDTHS = [1440, 1100, 900, 700, 400]


@needs_node
def test_policy_is_saturday_whole_weeks_with_a_date_format():
    got = _node("[" + ",".join(
        f"F.weekTicks({json.dumps(a)},{json.dumps(b)},{w})"
        for a, b in SPANS for w in WIDTHS) + "]")
    i = 0
    for a, b in SPANS:
        prev = 0
        for w in WIDTHS:
            p = got[i]; i += 1
            assert p["tickmode"] == "linear"
            assert p["tick0"] == "2000-01-01"
            assert date.fromisoformat(p["tick0"]).weekday() == 5   # Saturday
            weeks = p["dtick"] / WEEK_MS
            assert weeks == int(weeks) and weeks >= 1
            assert int(weeks) in (1, 2, 4, 8, 13, 26, 52) or weeks % 52 == 0
            assert p["tickformat"] in ("%b %-d", "%b %-d, %Y")
            # a narrower chart never crowds more labels in
            assert weeks >= prev
            prev = weeks
            ticks = _ticks(p, a, b)
            assert ticks, (a, b, w)
            assert all(d.weekday() == 5 for d in ticks), (a, b, w, ticks)


@needs_node
def test_week_53_and_year_boundary_ticks():
    # a six-week view over 2026 week 53: weekly ticks, the 53rd included
    p = _node('F.weekTicks("2026-12-05","2027-01-16",1100)')
    assert p["dtick"] == WEEK_MS and p["tickformat"] == "%b %-d"
    ticks = _ticks(p, "2026-12-05", "2027-01-16")
    assert date(2027, 1, 2) in ticks and date(2026, 12, 26) in ticks
    assert all(d.weekday() == 5 for d in ticks)
    # the reported bug: a Jan 10 point beside a Jan 11 tick
    p = _node('F.weekTicks("2025-10-18","2026-02-07",1440)')
    ticks = _ticks(p, "2025-10-18", "2026-02-07")
    assert date(2026, 1, 10) in ticks and date(2026, 1, 11) not in ticks


@needs_node
def test_span_and_width_pick_the_step():
    got = _node('[F.weekTicks("2025-10-18","2026-02-07",1440).dtick,'
                'F.weekTicks("2025-10-18","2026-02-07",700).dtick,'
                'F.weekTicks("2025-08-02","2026-07-25",700).dtick,'
                'F.weekTicks("2023-09-23","2026-07-04",700).tickformat,'
                'F.weekTicks("2025-10-18","2026-02-07",700).tickformat]')
    assert [g / WEEK_MS for g in got[:3]] == [1, 2, 8]
    assert got[3] == "%b %-d, %Y" and got[4] == "%b %-d"


@needs_node
def test_anchor_follows_the_data_weekday():
    got = _node('[F.anchorFor(["2026-01-03","2026-01-10",null]),'
                'F.anchorFor(["2026-01-04","2026-01-11"]),'
                'F.anchorFor(["2026-01-10","2026-01-11"]),'
                'F.anchorFor([0,1,2]), F.anchorFor([])]')
    # hub Saturdays; a custom dataset keyed on Sundays keeps Sundays;
    # mixed weekdays and numeric axes are left to Plotly
    assert got == ["2000-01-01", "2000-01-02", None, None, None]


@needs_node
def test_apply_layout_only_touches_dated_axes():
    got = _node(
        '[F.applyLayout({xaxis:{gridcolor:"#000"}},'
        '[{x:["2026-01-03","2026-01-10","2026-01-17"]}],700).xaxis,'
        # a weeks-since-August axis with month ticks is left alone
        'F.applyLayout({xaxis:{tickvals:[0,4],ticktext:["Aug","Sep"]}},'
        '[{x:[0,1,2]}],700).xaxis,'
        'F.applyLayout({xaxis:{}},[{x:[0,1,2]}],700).xaxis,'
        # an explicit range wins over the data extent
        'F.applyLayout({xaxis:{range:["2025-08-02","2026-07-25"]}},'
        '[{x:["2026-01-03"]}],700).xaxis]')
    dated, months, numeric, ranged = got
    assert dated["gridcolor"] == "#000" and dated["type"] == "date"
    assert dated["tick0"] == "2000-01-01" and dated["tickmode"] == "linear"
    assert "dtick" not in months and "tick0" not in months
    assert numeric == {}
    assert ranged["dtick"] == 8 * WEEK_MS


@needs_node
def test_shared_config_turns_plotly_tips_off():
    got = _node('[F.conf(), F.conf({displayModeBar:false})]')
    assert got[0]["showTips"] is False and got[0]["displaylogo"] is False
    assert got[1]["showTips"] is False and got[1]["displayModeBar"] is False


# ---------------------------------------------------------------- wiring

DATE_PAGES = ("forecast.html", "data.html", "model.html",
              "retro_dataset.html", "retro_season.html", "run.html",
              "sandbox.html")


def test_every_console_chart_draws_through_the_helper():
    for name in DATE_PAGES:
        t = (TEMPLATES / name).read_text()
        assert ('<script src="/static/plotly.min.js"></script>'
                '<script src="/static/charts.js"></script>') in t, name
    for p in list(TEMPLATES.glob("*.html")) + [STATIC / "sandbox.js"]:
        t = p.read_text()
        # no chart bypasses the helper (Plotly.Plots.resize and relayout
        # calls are fine)
        assert not re.search(r"(?<![\w.])Plotly\.(react|newPlot)\(", t), p.name
    assert "(root.FluCharts || root.Plotly).newPlot(" in \
        (STATIC / "sandbox.js").read_text()
    player = (STATIC / "player.js").read_text()
    assert "FluCharts : Plotly" in player and "PL.react(el.plot" in player
    assert "showTips: false" in player


def test_reports_inline_the_helper_and_adopt_their_figures(tmp_path):
    from app.core import report_season, report_v2
    assert report_v2.PLOTLY_CONFIG["showTips"] is False
    src = CHARTS.read_text()
    # the season report inlines charts.js ahead of the player
    pj = report_season._player_js()
    assert pj.startswith(src) and (STATIC / "player.js").read_text() in pj
    # the weekly report: a figure-bearing page carries the helper and
    # adopts every baked figure; a figure-less one carries neither
    fan = report_v2.fan_figure_from_quantiles(
        ["2026-01-03"], [10.0], ["2026-01-10", "2026-01-17"],
        {t: {str(lv): 10.0 for lv in report_v2.FAN_LEVELS}
         for t in ("2026-01-10", "2026-01-17")})
    det = {"OH": {"name": "Ohio", "fan": fan,
                  "cat": report_v2.cat_bar({"stable": 1.0}),
                  "table_rows": []}}
    html = report_v2.build_report("2026-01-03", {}, det, {},
                                  tmp_path / "a.html").read_text()
    assert src in html and "FluCharts.adoptAll()" in html
    bare = report_v2.build_report("2026-01-03", {}, {}, {},
                                  tmp_path / "b.html").read_text()
    assert "FluCharts" not in bare
    # a changed helper makes stored reports stale (rebuilt from the bundle)
    assert report_v2.builder_sources_mtime() >= CHARTS.stat().st_mtime


def test_report_fan_bands_are_fills_without_markers():
    # Plotly's default mode for a short trace is lines+markers, which drew
    # its own blue/orange/green dots on every band edge and legend swatch
    from app.core import report_v2
    fig = report_v2.fan_figure_from_quantiles(
        ["2026-01-03"], [10.0], ["2026-01-10", "2026-01-17"],
        {t: {str(lv): 10.0 + lv for lv in report_v2.FAN_LEVELS}
         for t in ("2026-01-10", "2026-01-17")})
    bands = [t for t in fig.data if t.fill == "toself"]
    assert len(bands) == 3 and all(t.mode == "lines" for t in bands)
