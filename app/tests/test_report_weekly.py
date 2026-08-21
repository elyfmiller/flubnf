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
    # land, and the map/legend/gap language survives
    html = build_report(
        "2098-01-03", {}, {}, {}, tmp_path / "r.html", elapsed_s=3725.0,
        settings_html='<p class="hint runsettings"><strong>Run settings:'
                      "</strong> engine pf</p>").read_text()
    assert "Run wall time: 1:02:05" in html
    assert "Run settings" in html
    assert "no data (reporting gap)" in html
    assert "shown as gaps, never interpolated" in html


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
