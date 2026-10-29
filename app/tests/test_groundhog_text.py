"""The Groundhog's record and description: the size-matched form that ships
since 2026-10-23 (README, Measured record), on Home, Methods and its model
page, in its diagrams and in its Model settings help."""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import knobs as K                       # noqa: E402
from app.ui.routes.methods import _choice             # noqa: E402
from app.ui.server import app as srv                  # noqa: E402
from app.ui.server import templates                   # noqa: E402

client = TestClient(srv)

def _text(html):
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _diagrams():
    return templates.env.get_template("diagrams.html").module


def test_the_groundhog_is_described_with_its_size_matched_donors():
    how = _text(client.get("/methods").text)
    assert ("within each half, donor weeks whose count is near the "
            "jurisdiction's newest count carry the most weight (since "
            "2026-10-23)") in how
    assert ("the size-matched donors (since 2026-10-23) separate the "
            "Groundhog from the bare calendar analogue") in how
    page = _text(client.get("/model/analogue").text)
    assert "own and similar-sized weeks" in page
    assert "weeks sized like its latest count the most" in page
    dg = _diagrams()
    assert "weeks sized like its newest count the most" in str(
        dg.analogue_mech())
    assert "weeks sized like its newest count the most" in str(
        dg.eq_analogue())


def test_the_own_state_weight_no_longer_calls_0_the_pooled_form():
    # 0 alone still runs the size-matched kernel
    help_ = K.BY_KEY["groundhog.own_share"].help
    assert "pooled form" not in help_ and help_.endswith("0 drops it.")


def test_a_choice_word_that_starts_with_its_value_is_not_repeated():
    assert _choice("groundhog.aux", "none") == "none (bare analogue)"
    assert _choice("pf.initialization", "rand") == "random draws (rand)"
    assert _choice("groundhog.aux", "both") == "FluSurv-NET and ILI+ (both)"
    assert "(bare analogue) (none)" not in client.get("/methods").text


def test_the_ratio_figure_counts_one_ratio_per_donor_week():
    # the fold says one state gives about five donors per season
    fig = str(_diagrams().analogue_ratios())
    assert "one ratio per donor week" in fig
    assert "Each donor week contributes one growth ratio" in fig
    assert "donor season" not in fig


def test_the_groundhog_fan_spans_the_four_weeks_it_forecasts():
    fig = str(_diagrams().analogue_mech())
    pts = re.search(r'<polygon points="([^"]+)" fill="var\(--gold-bright\)"',
                    fig).group(1)
    xs = [float(p.split(",")[0]) for p in pts.split()]
    week = 745 / 52
    assert abs((max(xs) - min(xs)) / week - 4) < 0.1
    median = re.search(r'<path d="M430,140 C[^"]*?(\d+),\d+" fill="none"\s+'
                       r'stroke="var\(--gold\)"', fig)
    assert median and float(median.group(1)) == max(xs)
