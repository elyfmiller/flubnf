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
    return p.read_text(encoding="utf-8")


def test_the_report_is_written_and_served_whatever_the_locale(tmp_path):
    """Windows' default text encoding is its code page (cp1252), which
    cannot hold the report's symbols (the Cmd sign), and a console started
    without PYTHONUTF8 ended every run without a report. test-windows runs
    in UTF-8 mode, which hides that, so a child with UTF-8 mode off and an
    ASCII locale (the runner's own cp1252 on Windows, where LC_ALL has no
    say) builds the report and reads it back as /output/report does."""
    import os
    import subprocess
    repo = Path(__file__).resolve().parents[2]
    out = tmp_path / "r.html"
    code = ("import sys\n"
            "from pathlib import Path\n"
            "from app.core.report_v2 import build_report\n"
            "from app.ui.routes.output import _stored_report_text\n"
            f"p = build_report('2098-01-03', {{}}, {{}}, {{}}, Path({str(out)!r}), "
            "model_label='\\u2318')\n"
            "print(sys.flags.utf8_mode, '\\u2318' in _stored_report_text(p))\n")
    env = dict(os.environ, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0",
               LC_ALL="C", LANG="C", PYTHONPATH=str(repo))
    r = subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=300)
    assert r.returncode == 0, r.stderr[-2000:]
    assert r.stdout.split() == ["0", "True"]
    assert "⌘" in out.read_text(encoding="utf-8")


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
    """The report embeds the console's full theme system (four theme blocks
    plus both modifiers, verbatim from nau.css), boots from the console's
    localStorage keys with OS fallbacks, and with charts adds a retint pass
    over the figures' baked palette."""
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
        {}, tmp_path / "c.html").read_text(encoding="utf-8")
    assert "Plotly.react(g,g.data,g.layout)" in charted
    # the retint map resolves the figures' baked literals from the chrome's
    # tokens (category bars, ok/bad, the accent via --gold), so the CV-safe
    # modifier reaches every chart encoding as it reaches the map
    for pair in ('MAP["#151729"]=css("--card"', 'MAP["#E9EAF4"]=css("--ink"',
                 'MAP["#9AA1C4"]=css("--mut"', 'MAP["#262A45"]=css("--line"',
                 'MAP["#b9b09b"]=css("--cat-stable"',
                 'MAP["#2e7d4f"]=css("--cat-large-decrease"',
                 'MAP["#c0392b"]=css("--cat-large-increase"',
                 'MAP["#4CC38A"]=css("--ok"', 'MAP["#FB4653"]=css("--bad"',
                 'MAP["#34C0F0"]=css("--gold"'):
        assert pair in charted, pair
    # the pass re-runs from a per-plot snapshot on themechange, retinting in
    # both directions; the two shipped members' colours and band fills
    # follow the report's own tokens (the Groundhog's gold is darker on a
    # light card), the other members' literals are left alone
    assert "addEventListener('themechange',pass)" in charted
    assert "_flubnfBaked" in charted
    from app.core.report_v2 import MEMBER_COLORS, band_literal
    retint = charted.split("function pass()", 1)[1].split("</script>", 1)[0]
    for m in ("pf", "analogue"):
        assert f'MAP["{MEMBER_COLORS[m]}"]=css("--model-{m}"' in retint, m
        for lvl in ("95", "50"):
            assert (f'MAP["{band_literal(m, lvl)}"]=css("--rp-band-{m}-{lvl}"'
                    in retint), (m, lvl)
    assert f'MAP["{MEMBER_COLORS["pf_filter"]}"]' not in retint
    for tok in ("--model-pf:", "--model-analogue:", "--rp-band-pf-95:"):
        assert tok in charted, tok


def test_weekly_report_map_swatches_ride_the_category_tokens(tmp_path):
    # the legend and confidence swatches resolve through --cat-*, so the
    # color-vision modifier reaches them exactly as it reaches the map
    # (the kit's legend chips: the swatch color is the chip's --sw)
    html = _build(tmp_path)
    assert 'style="--sw:var(--cat-increase, #e8a33d)"' in html
    assert "--sw:var(--cat-large-decrease, #2e7d4f)" in html
    # the confidence chips mix the same token over the card
    assert ("--sw:color-mix(in srgb,var(--cat-increase, #e8a33d) 64%,"
            "var(--card))") in html


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
    # the footer and settings block still land; the gap claim renders only
    # for card-less states inside the recorded scope, others read not fitted,
    # and with no recorded scope only 'no data' is claimed
    html = build_report(
        "2098-01-03", {}, {}, {}, tmp_path / "r.html", elapsed_s=3725.0,
        settings_html='<p class="hint runsettings"><strong>Run settings:'
                      "</strong> engine pf</p>",
        fitted_fips=["39"]).read_text(encoding="utf-8")
    # the run card's stat in words, the settings folded under "Run
    # details"; no explainers (Ely, 2026-10-07: the figures speak)
    assert "<dt>Run time" in html
    assert '<span class="uk-stat-v" id="runtime">1 h 2 min 5 s</span>' in html
    assert "Wall time" not in html
    assert '<span class="uk-fold-sum">Run details</span>' in html
    assert "Run settings" in html
    assert "</span>no data<" in html
    assert "Gaps are shown, never filled in." not in html
    assert "not fitted in this run" in html
    # no recorded scope: the gap is not asserted for states nobody checked
    html2 = build_report(
        "2098-01-03", {}, {}, {}, tmp_path / "r2.html").read_text(encoding="utf-8")
    assert "</span>no data<" not in html2
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
    assert "Oracle SIHRS relWIS" in html
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


def test_a_state_with_data_but_no_forecast_is_named_in_the_legend(tmp_path):
    """A card without probabilities (the Groundhog skips a last count of
    0) is filled like no data; the legend says what that fill means."""
    card = {"fips": "50", "name": "Vermont", "abbr": "VT", "probs": None,
            "hover_html": ""}
    html = build_report("2098-01-03", {"VT": card}, {}, {},
                        tmp_path / "r.html", fitted_fips=["50"]
                        ).read_text(encoding="utf-8")
    assert "</span>no forecast<" in html
    assert "No-forecast states have data but no forecast" not in html
    html2 = build_report("2098-01-03", {}, {}, {}, tmp_path / "r2.html",
                         fitted_fips=["50"]).read_text(encoding="utf-8")
    assert "</span>no forecast<" not in html2


def test_state_panel_and_national_card_use_the_hub_rate_change_rule():
    """The one-week-ahead state panel reads hub horizon 0, the same cuts as
    its map card, and the national card uses the hub's US population rather
    than a rounded constant."""
    src = (Path(__file__).resolve().parents[2]
           / "app/ui/pipeline.py").read_text(encoding="utf-8")
    assert 'pop_l = us_pop if fips_l == "US" else int(n2p.get(loc, 1e6))' \
        in src
    # both fan sources (PF samples, Groundhog grid) read horizon 0
    assert 'src["0"], float), lo_l, pop_l, 0)' in src
    assert "grid[0], lo_l, pop_l, 0)" in src
    assert "q1, lo_us, us_pop, 0)" in src
    assert "q1, lo_us, 340_000_000, 0)" not in src


def test_weekly_report_carries_the_ui_kit(tmp_path):
    """The report wears the console's kit offline: the kit's sheet and
    behavior inlined, the face and the per-theme marks as data: URIs, the
    map's explainer in a "?" and the view switch as the kit's segmented
    control, whose aria-pressed the page script flips."""
    from app.core import html_page
    html = build_report("2098-01-03", {}, {}, {}, tmp_path / "r.html",
                        national_map_html="<svg></svg>").read_text(encoding="utf-8")
    assert html_page.kit_css() in html and html_page.kit_js() in html
    assert "@font-face" in html and "data:font/woff2;base64," in html
    assert '[data-theme="dracula"]{--logo:url("data:image/svg+xml;base64,' \
        in html
    assert 'class="mark" aria-hidden="true"' in html
    assert 'aria-describedby="tip-map"' not in html     # no "?" here
    assert '<div class="uk-seg" role="group" aria-label="Map view">' in html
    assert 'id="btn-state-view" class="on" aria-pressed="true"' in html
    assert "bN.setAttribute('aria-pressed'" in html
    # the stored text size is followed too
    assert "localStorage.getItem('fontsize')" in html
