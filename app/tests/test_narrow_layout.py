"""The Forecast page at phone width (420px): no horizontal page scroll, on
the hub view and on a dataset view.

The root cause was the one-column fallback of .cols below 900px: a bare
`1fr` track is minmax(auto, 1fr), whose minimum is the widest item's
min-content width, so the latest-run results table (nowrap row headers)
and the fan card's nav row (a 230px select between buttons) widened the
column, and the page, past the screen. The track is minmax(0,1fr), like
the desktop layout's second track, and the fan's nav row wraps. Layout is
measured in a browser; these pin the rules that make it hold.
"""
import re
from pathlib import Path

NAU = (Path(__file__).resolve().parents[1] / "ui" / "static"
       / "nau.css").read_text()
JOINED = " ".join(NAU.split())


def _rules(selector: str) -> list:
    """Every declaration block of `selector`, inside media queries too."""
    return [m.group(1) for m in re.finditer(
        r"(?:^|[}\s])" + re.escape(selector) + r"\{([^}]*)\}", NAU)]


def test_the_one_column_fallback_can_shrink_below_its_content():
    narrow = re.search(r"@media\(max-width:900px\)\{\.cols\{([^}]*)\}\}",
                       NAU)
    assert narrow, "the .cols fallback below 900px is gone"
    assert narrow.group(1) == "grid-template-columns:minmax(0,1fr)"
    # no .cols track anywhere may be a bare 1fr (an auto minimum)
    for body in _rules(".cols"):
        cols = re.search(r"grid-template-columns:([^;]*)", body)
        if cols:
            assert not re.search(r"(^|\s)1fr", cols.group(1)), cols.group(1)


def test_the_desktop_layout_is_unchanged():
    assert (".cols{display:grid;grid-template-columns:minmax(260px,360px) "
            "minmax(0,1fr);gap:.75rem; align-items:start}") in JOINED


def test_carousel_rows_wrap_instead_of_scrolling_the_card():
    body = _rules(".carousel")
    assert body and "flex-wrap:wrap" in body[0]
