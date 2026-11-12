"""The weekly report's look (bug hunt 2026-10-25, UI-03 and UI-04),
changed in one commit so stored reports are rebuilt once.

  * On light cards the report draws the Groundhog in the console's own
    gold, #806000 (nau.css's light themes), not #A87300.
  * The charts' toolbar buttons show the console's focus ring in the
    report too (Plotly's own 1px black ring is lost on a dark card).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import report_v2                                 # noqa: E402

STATIC = Path(__file__).resolve().parents[1] / "ui" / "static"


def _rule(css: str, selector: str) -> str:
    """The declarations of the one rule whose selector list is `selector`."""
    m = re.search(re.escape(selector) + r"\{([^}]*)\}", css)
    assert m, selector
    return m.group(1)


def _luminance(hex_color: str) -> float:
    c = [int(hex_color.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def _contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_the_reports_groundhog_on_light_cards_is_the_consoles_gold():
    css = (STATIC / "nau.css").read_text(encoding="utf-8")
    light = [b for b in re.findall(r"\{([^{}]*--scheme:light[^{}]*)\}", css)
             if "--model-analogue:" in b]
    assert light
    golds = {re.search(r"--model-analogue:(#[0-9A-Fa-f]{6})", b).group(1)
             for b in light}
    assert golds == {report_v2.ANALOGUE_ON_LIGHT} == {"#806000"}
    # 3:1 or more on every light theme's card
    for b in light:
        card = re.search(r"--card:(#[0-9A-Fa-f]{6})", b)
        if card:
            assert _contrast("#806000", card.group(1)) >= 3, card.group(1)
    # the page the report serves names it for light cards
    assert "--model-analogue:#806000" in report_v2.page_style()
    assert "--model-analogue:#A87300" not in report_v2.page_style()


def test_the_reports_chart_toolbar_shows_the_consoles_focus_ring():
    style = report_v2.page_style()
    rule = _rule(style, ".plotly .modebar .modebar-group .modebar-btn:focus-visible")
    assert "outline:var(--focus-w,2px) solid var(--gold)" in rule
    # a chartless page's style never reads as charted (legacy_theme_carry)
    assert "js-plotly-plot" not in style and "Plotly.newPlot" not in style

