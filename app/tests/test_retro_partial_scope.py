"""The Retrospective's US national row and the pooled figure's labels on a
replay of part of the hub set (the 2026-10-25 bug hunt, G08).

  * a replay of fewer than the 52 jurisdictions has no sum of states: its
    states do not add up to the nation (RE-01);
  * a replay that fitted US is labelled fitted before its scores exist
    (scoring pending or failed), as its forecast is drawn (UI-11);
  * the pooled note names the replay's own jurisdictions and calls the US
    cell "their sum" only when it is one (RE-14); the live scores say how
    many jurisdictions they pool, whichever location the forecast detail
    shows (RE-10).
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import retro                                  # noqa: E402
from app.core import us_national as usn                     # noqa: E402
from app.ui.routes import retro as ui_retro                 # noqa: E402
from app.ui.templating import templates                     # noqa: E402

from test_results_prep import (SEASON, _groundhog_only,     # noqa: E402
                               _mk_tree, _truth, _unscored)
from test_retro_player import CONTEXT                       # noqa: E402

def _states():
    from flubnf.settings import load_locations
    return [n for n in load_locations().location_name if not usn.is_us(n)]


def _settings(root, **settings):
    meta = retro.read_meta(root)
    meta["settings"] = {**(meta.get("settings") or {}), **settings}
    retro.write_meta(root, meta)


def _scores(locs=("Ohio", "Utah")):
    n = len(locs)
    return pd.DataFrame({"location": list(locs), "model": ["analogue"] * n,
                         "wis": [1.0] * n, "base_wis": [2.0] * n})


# ---------------------------------------------------------- the US national row

def test_a_replay_of_part_of_the_52_has_no_sum_of_states(tmp_path):
    root = tmp_path / SEASON
    _settings(root, locations=["Arizona", "Texas"], national=False)
    us = usn.resolve(root, _scores(("Arizona", "Texas")))
    assert us.provenance == usn.OFFICIALS_ONLY and not us.has_scores
    assert us.reason == ("only 2 of the 52 jurisdictions were replayed, so "
                         "their forecasts do not sum to the nation")
    # the whole set is still summed (nothing stored to sum here: its own
    # reason, not this one)
    _settings(root, locations=_states() + ["US"], national=False)
    us = usn.resolve(root, _scores(("Arizona", "Texas")))
    assert "were replayed" not in us.reason


def test_a_replay_that_fitted_us_is_labelled_fitted_before_its_scores(
        tmp_path, monkeypatch):
    root = _groundhog_only(_mk_tree(tmp_path))
    _unscored(monkeypatch, tmp_path, _truth())
    _settings(root, locations=["Ohio", "Utah", "US"], national=True)
    us = usn.resolve(root, _scores())
    assert us.provenance == usn.FITTED and us.label == "US national (fitted)"
    # the season page, its scoring not done: the player's US label
    ctx = ui_retro.season_page_context(root, SEASON)
    assert ctx["us"]["provenance"] == usn.FITTED
    assert ctx["us"]["label"] == "US national (fitted)"


# ------------------------------------------------------------- the pooled words

def test_the_pooled_note_names_the_replays_jurisdictions_and_the_us_cell():
    """One static sentence said 'the fitted states, DC and Puerto Rico' and
    called a fitted US 'their sum', whatever the replay covered."""
    assert usn.pooled_scope_note(6) == (
        "Pooled relWIS covers the 6 replayed jurisdictions; the US national "
        "cell is scored apart and never joins the pooled average.")
    assert usn.pooled_scope_note(52) == usn.POOLED_SCOPE_NOTE == (
        "Pooled relWIS covers the 50 states, DC and Puerto Rico; the US "
        "national cell is scored apart and never joins the pooled average.")
    assert usn.pooled_scope_note(52, usn.FITTED) == usn.POOLED_SCOPE_NOTE
    assert usn.pooled_scope_note(52, usn.AGGREGATED) == (
        "Pooled relWIS covers the 50 states, DC and Puerto Rico; the US "
        "national cell, their sum, is scored apart and never joins the "
        "pooled average.")
    assert usn.pooled_scope_note(1, usn.OFFICIALS_ONLY).startswith(
        "Pooled relWIS covers the 1 replayed jurisdiction;")


def test_the_live_scores_say_they_are_pooled():
    def stats(**kw):
        html = templates.env.get_template("retro_season.html").render(
            **dict(CONTEXT, **kw))
        return html.split('class="playstats"', 1)[1].split("</table>", 1)[0]
    assert '<span class="uk-tag">52 jurisdictions pooled</span>' in stats(
        pooled_n=52)
    assert '<span class="uk-tag">1 jurisdiction pooled</span>' in stats(
        pooled_n=1)
    assert "uk-tag" not in stats()                      # no scope known
