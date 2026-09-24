"""Week arithmetic in the page scripts stays in UTC.

A date string plus local-time days lands a day early across a DST change
(America/New_York: 2026-02-28 + 2 weeks drew on Friday 2026-03-13), and
local midnight read back with toISOString is the day before in any zone
east of UTC. The Forecast tab's live anchor line also picked the oldest
archived week, because the vintage list runs newest first."""
import re
from pathlib import Path

TPL = Path(__file__).resolve().parents[1] / "ui" / "templates"


def test_forecast_and_model_pages_add_weeks_in_utc():
    for name in ("forecast.html", "model.html"):
        text = (TPL / name).read_text()
        assert not re.search(r"\.setDate\(", text), name
        assert not re.search(r"\.getDay\(\)", text), name
        assert "T00:00:00Z" in text, name


def test_the_live_anchor_takes_the_newest_week_on_or_before_the_day():
    text = (TPL / "forecast.html").read_text()
    fn = text[text.index("function anchorFor"):text.index("function paint")]
    # never the last element of a filtered list: VS runs newest first
    assert "earlier[earlier.length - 1]" not in fn
    assert "v > a" in fn
