"""The Retrospective option's cost as the server first renders it, for a
remembered Particles or Independent Runs the server's check refuses
(review 3 of #93, re-check R5, the server's half).

The page's script reads both fields as the check does (retro_progress.js
knobWhole) and gives no figure for a refused value; the server's own
first render (routes/retro._form_costs) read digits only, so a value
just past the field's max was priced as if it would run, and "20,000" or
"1e4" at the default. Now both read alike: the option as served is what
the script says on the same page before any change.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import served_dom as SD                                    # noqa: E402
from app.ui.routes import retro as ui_retro                # noqa: E402

from test_retro_cost_refused import (                       # noqa: E402
    BASE, EST_JS, PF_OPT, SAID, SEASON, TICKER_JS, _server_reads, _want,
    client, needs_js, world)                                # noqa: F401

#: an empty retro root and SEASON (test_retro_cost_refused.world) for each
pytestmark = pytest.mark.usefixtures("world")

#: (field, value as remembered): just past each edge, written other ways,
#: and the review's long one
CASES = [("particles", v) for v in (
    "100001", "200000", "999", "100000", "1000", "1e4", "2.5", "abc",
    "20,000", "1_0000", " 5000 ", "+5000", "-5000", "9" * 25)] + [
    ("replicates", v) for v in ("11", "0", "10", "1,0", "x")]


def _served(field: str, value: str) -> str:
    ui_retro._last_retro_form.clear()
    ui_retro._last_retro_form.update({
        "season": SEASON, "locations": "panel6", "engine": "pf",
        field: value})
    return client.get("/retro").text


def _expected(field: str, value: str) -> str:
    if field == "particles":
        return _want(_server_reads("pf.particles", value), 3)
    return _want(10_000, _server_reads("pf.replicates", value))


@pytest.mark.parametrize("field, value", CASES)
def test_the_first_render_prices_what_the_check_would_run(field, value):
    """No figure for a value the check refuses; the figure for the value
    it reads otherwise."""
    html = _served(field, value)
    assert PF_OPT.search(html).group(1) == _expected(field, value)


def test_both_kinds_are_among_the_cases():
    refused = [c for c in CASES if _expected(*c) == BASE]
    assert 5 < len(refused) < len(CASES) - 5


@needs_js
def test_the_script_keeps_what_the_server_rendered(tmp_path):
    """The script, run on each page as served, says the same before any
    change: no figure appears or goes when it loads."""
    got, want = [], []
    for i, (field, value) in enumerate(CASES):
        html = _served(field, value)
        want.append(PF_OPT.search(html).group(1))
        got.append(SD.run(tmp_path / str(i), html, [EST_JS, TICKER_JS],
                          SAID + "return said();"))
    assert got == want
