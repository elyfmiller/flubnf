"""Weekly report identity: the report_v2 export wears the console's design
system. Locks the token values, the FluBNF wordmark, the DM Sans face with
no webfont fetch, self-containment, the print stylesheet, and the
one-relWIS rule on the score table the report embeds."""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.report_v2 import build_report          # noqa: E402


def _build(tmp_path):
    p = build_report("2098-01-03", {}, {}, {}, tmp_path / "r.html")
    return p.read_text()


def test_weekly_report_wears_the_console_tokens(tmp_path):
    html = _build(tmp_path)
    # nau.css dark-theme values, verbatim, so a color means the same thing
    # in the console and in the exported file
    for token in ("--bg:#0C0D17", "--card:#151729", "--ink:#E9EAF4",
                  "--mut:#9AA1C4", "--line:#262A45", "--accent:#34C0F0",
                  "--ok:#4CC38A", "--bad:#FB4653"):
        assert token in html, token
    # the brand face with a system fallback, and tabular numerals where
    # digits align
    assert '"DM Sans",system-ui' in html
    assert "font-variant-numeric:tabular-nums" in html
    # the wordmark, exactly as the console's navbar writes it
    assert "<em>Flu</em>BNF" in html
    # the alert classes exist so any embedded relWIS coloring applies
    assert ".ok{color:var(--ok)}.bad{color:var(--bad)}" in html
    assert ".relwis{font-variant-numeric:tabular-nums" in html


def test_weekly_report_fetches_nothing(tmp_path):
    html = _build(tmp_path)
    assert "<script src" not in html
    assert "<link" not in html
    assert "@import" not in html
    assert "fonts.googleapis" not in html and "fonts.gstatic" not in html
    # the only URL-shaped strings are XML namespace declarations on the
    # inline SVG map, which are identifiers, never fetched
    for m in re.finditer(r"https?://[^\"'\s<)]*", html):
        assert m.group(0).startswith("http://www.w3.org/"), m.group(0)


def test_weekly_report_is_theme_aware(tmp_path):
    """The report embeds the console's full theme system and resolves it
    at open: all four theme token blocks plus both accessibility modifier
    blocks, verbatim from nau.css; a boot script that reads the console's
    localStorage keys same-origin and falls back to the OS preferences
    standalone; and, when charts are embedded, a retint pass that re-reads
    the resolved tokens and re-resolves the figures' baked palette."""
    import numpy as np

    from app.core import report_v2
    html = _build(tmp_path)
    for sel in ('[data-theme="dark"]{', '[data-theme="paper"]{',
                '[data-theme="dim"]{', '[data-contrast="high"]{',
                '[data-vision="cvd"]{'):
        assert sel in html, sel
    assert "--bg:#F1EFF7" in html                   # the light palette too
    assert report_v2.theme_token_css() in html      # nau.css verbatim
    for probe in ("localStorage.getItem('theme')",
                  "localStorage.getItem('contrast')",
                  "localStorage.getItem('vision')",
                  "prefers-color-scheme", "prefers-contrast"):
        assert probe in html, probe
    # print wins the cascade: it is the last token statement in the sheet
    assert html.rindex("@media print") > html.rindex('[data-vision="cvd"]{')
    # a chartless report ships no retint pass; a charted one must
    assert "Plotly.react(g,g.data,g.layout)" not in html
    rng = np.random.default_rng(5)
    f_t = ["2098-01-10", "2098-01-17", "2098-01-24", "2098-01-31"]
    q = report_v2.fan_quantiles(
        f_t, {t: rng.gamma(4.0, 30.0, 300).tolist() for t in f_t})
    fan = report_v2.fan_figure_from_quantiles(
        ["2098-01-03"], [110.0], f_t, q, title="t")
    charted = report_v2.build_report(
        "2098-01-03", {}, {"OH": {"name": "Ohio", "fan": fan,
                                  "cat": report_v2.cat_bar({"stable": 1.0}),
                                  "table_rows": []}},
        {}, tmp_path / "c.html").read_text()
    assert "Plotly.react(g,g.data,g.layout)" in charted
    # the retint map covers the figures' baked literals, resolved from the
    # SAME tokens the chrome wears: category bars, the semantic ok/bad
    # pair, and the accent through --gold (its readable variant on light
    # grounds), so the color-vision modifier reaches every chart-internal
    # category and ok/bad encoding exactly as it reaches the map
    for pair in ('MAP["#151729"]=css("--card"', 'MAP["#E9EAF4"]=css("--ink"',
                 'MAP["#9AA1C4"]=css("--mut"', 'MAP["#262A45"]=css("--line"',
                 'MAP["#b9b09b"]=css("--cat-stable"',
                 'MAP["#2e7d4f"]=css("--cat-large-decrease"',
                 'MAP["#c0392b"]=css("--cat-large-increase"',
                 'MAP["#4CC38A"]=css("--ok"', 'MAP["#FB4653"]=css("--bad"',
                 'MAP["#34C0F0"]=css("--gold"'):
        assert pair in charted, pair
    # the pass re-runs from a per-plot snapshot on themechange, so a host
    # that flips tokens live (the console toggle, or a headless audit
    # dispatching the event) retints in BOTH directions; member colors are
    # deliberately not in the map (the palette is dichromat-spaced)
    assert "addEventListener('themechange',pass)" in charted
    assert "_flubnfBaked" in charted
    from app.core.report_v2 import MEMBER_COLORS
    retint = charted.split("function pass()", 1)[1].split("</script>", 1)[0]
    for m, col in MEMBER_COLORS.items():
        if m == "ensemble":        # the ensemble literal IS the accent cyan
            continue
        assert f'MAP["{col}"]' not in retint, m


def test_weekly_report_map_swatches_ride_the_category_tokens(tmp_path):
    # the legend and confidence swatches resolve through --cat-*, so the
    # color-vision modifier reaches them exactly as it reaches the map
    html = _build(tmp_path)
    assert 'style="background:var(--cat-increase, #e8a33d)' in html
    assert "background:var(--cat-large-decrease, #2e7d4f)" in html


def test_weekly_report_carries_a_print_stylesheet(tmp_path):
    html = _build(tmp_path)
    assert "@media print" in html
    pr = html.split("@media print", 1)[1]
    # on paper the console's light theme takes over: light surface, the
    # LANL Blue ink, and the light-theme ok/bad pair
    for v in ("#FFFFFF", "#000F7E", "--ok:#177245", "--bad:#C42840"):
        assert v in pr, v
    # interactive chrome stays on screen
    assert "display:none!important" in pr


def test_weekly_report_keeps_its_build_contract(tmp_path):
    # restyle, not regress: the wall-time footer and settings block still
    # land, and the map/legend/gap language survives WHERE IT WAS CHECKED:
    # the gap claim renders only for card-less states inside the run's
    # recorded scope; the rest are stated as not fitted, and a report with
    # no recorded scope claims only 'no data' (review finding 2026-08)
    html = build_report(
        "2098-01-03", {}, {}, {}, tmp_path / "r.html", elapsed_s=3725.0,
        settings_html='<p class="hint runsettings"><strong>Run settings:'
                      "</strong> engine pf</p>",
        fitted_fips=["39"]).read_text()
    assert "Run wall time: 1:02:05" in html
    assert "Run settings" in html
    assert "no data (reporting gap)" in html
    assert "shown as gaps, never interpolated" in html
    assert "not fitted in this run" in html
    # no recorded scope: the gap is not asserted for states nobody checked
    html2 = build_report(
        "2098-01-03", {}, {}, {}, tmp_path / "r2.html").read_text()
    assert "no data (reporting gap)" not in html2
    assert "no data in this view" in html2
    assert "not fitted in this run" not in html2


def test_summary_table_applies_the_relwis_rule():
    from app.core.scoring import summary_table_html
    df = pd.DataFrame([
        {"location": "Ohio", "fips": "39", "horizon": 1,
         "wis": 1.0, "base_wis": 2.0},
        {"location": "Ohio", "fips": "39", "horizon": 2,
         "wis": 1.0, "base_wis": 2.0},
        {"location": "Utah", "fips": "49", "horizon": 1,
         "wis": 3.0, "base_wis": 2.0},
    ])
    html = summary_table_html(df)
    # member label in the header, never a bare "relWIS"
    assert "PF-SIHRS relWIS" in html
    # ok/bad by the below-1 rule
    assert '<td class="num ok">0.500</td>' in html
    assert '<td class="num bad">1.500</td>' in html
    # cell coverage rides each score
    assert '<td class="num hint">2</td>' in html      # Ohio, 2 cells
    assert '<td class="num hint">1</td>' in html      # Utah, 1 cell
    # the pooled row wears the same rule and states its coverage
    assert "All locations" in html
    assert '<td class="num ok">0.833</td>' in html    # 5/6
    assert '<td class="num hint">3</td>' in html
    # empty frame: honest placeholder, no invented numbers
    empty = summary_table_html(pd.DataFrame())
    assert "hint" in empty and "relWIS" in empty and "<table" not in empty
