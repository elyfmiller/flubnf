"""The season page's player and score tables: what a student sees when a
visit opens on a week with no data, when a stored week had no FluSight
round, under the week scrubber, after a click on a state name, and when
nothing is scored or scoring failed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.tests.test_retro_player import CONTEXT, PLAYER_JS       # noqa: E402
from app.ui.routes.retro import score_error_plain                # noqa: E402
from app.ui.server import templates                              # noqa: E402
from app.ui.templating import _month_ticks_for_dates             # noqa: E402

SEASON_T = (Path(__file__).resolve().parents[1] / "ui" / "templates"
            / "retro_season.html").read_text(encoding="utf-8")

#: the message score_season raises when the hub clone has no baseline
NO_BASELINE = ("FileNotFoundError: the hub clone has no "
               "model-output/FluSight-baseline (sparse checkout predates the "
               "baseline requirement). Press Update data on the Data tab to "
               "fetch it, then rescore.")


def _render(**kw):
    return templates.env.get_template("retro_season.html").render(
        **dict(CONTEXT, **kw))


# ---------------------------------------- RE-04: a visit on a no-data week

def test_a_visit_that_opens_on_a_no_data_week_keeps_every_member():
    # the placeholder forecasts nothing; the controls are built from the
    # stored week it borrows its truth from, so the replay's own models
    # stay offered for the whole visit
    fetch = PLAYER_JS.split("NDP[w] = cfg.getPayload(src).then(", 1)[1] \
        .split("});", 1)[0]
    assert fetch.index("if(pl) buildControls(pl);") \
        < fetch.index("return noDataPayload(pl, w);")


# ------------------------------------------- RE-15: the scrubber's months

def test_the_scrubber_labels_the_first_weeks_month_too():
    weeks = ["2025-08-30", "2025-09-20", "2025-11-15", "2025-11-22",
             "2025-12-06"]
    assert _month_ticks_for_dates(weeks) == [(1, "Sep"), (2, "Nov"),
                                             (4, "Dec")]
    assert _month_ticks_for_dates(weeks, first=True) == [
        (0, "Aug"), (1, "Sep"), (2, "Nov"), (4, "Dec")]
    html = _render(timeline=["2098-11-07", "2098-11-14", "2098-12-05"])
    ticks = html.split('<span class="rt-ticks"', 1)[1].split("</span></span>", 1)[0]
    assert '<span style="--f:0.0000">Nov</span>' in ticks
    assert '<span style="--f:1.0000">Dec' in ticks


def test_the_scrubbers_months_are_fitted_inside_the_track_and_apart():
    # measured in the browser (the track is 210 to 600 px wide): an end
    # label is pulled inside, one that would touch the label before it is
    # left out, again on every resize
    fit = SEASON_T.split("function fitTicks(){", 1)[1].split("\n }\n", 1)[0]
    assert "s.style.transform = 'none'" in fit
    assert "s.style.transform = 'translateX(-100%)'" in fit
    assert "if(r.left < end + gap) s.hidden = true;" in fit
    # the season's last month keeps its label over the one before it
    assert "if(last && last.hidden){" in fit
    assert "setTimeout(fitTicks, 150)" in SEASON_T


# ---------------------------- UI-01: a state name brings the player up

def test_a_state_name_scrolls_after_the_click_guard_lets_go():
    # base.html's guard undoes any scroll within two frames of a click; an
    # instant scroll (reduced motion) was undone, so it waits two frames
    click = SEASON_T.split("button.rt-locbtn[data-loc]", 1)[1] \
        .split("\n });", 1)[0]
    assert ("requestAnimationFrame(() => requestAnimationFrame(() =>\n"
            "     card.scrollIntoView(") in click


# ------------------------------- UI-18: the per-state card with no rows

def test_a_season_with_no_scored_state_shows_an_empty_state_not_headers():
    html = _render(states=[], us_row=None, season_models=["analogue"])
    card = html.split('id="statefold"', 1)[1].split("</details>", 1)[0]
    assert 'id="rs-states-none"' in card
    assert "Arrives with the first scored week" in card
    assert 'id="sf-table"' not in card and 'id="sf-filter"' not in card
    # a scored state: the table and its filter
    card = _render(season_models=["analogue"]).split(
        'id="statefold"', 1)[1].split("</details>", 1)[0]
    assert 'id="sf-table"' in card and 'id="rs-states-none"' not in card


# ----------------------------- UI-20: a scoring failure in plain words

def test_a_known_scoring_failure_reads_in_plain_words():
    assert score_error_plain(NO_BASELINE) == (
        "The FluSight baseline forecasts are not on this computer yet. "
        "Update data from the Data tab, then open this page again.")
    assert score_error_plain("ValueError: boom") == ""
    assert score_error_plain("") == ""
    html = _render(heads={}, us=None, us_row=None, score_error=NO_BASELINE,
                   score_plain=score_error_plain(NO_BASELINE))
    alert = html.split('id="rs-scorefail"', 1)[1].split("</span></div>", 1)[0]
    text = alert.split('<details', 1)[0]
    assert "The FluSight baseline forecasts are not on this computer" in text
    # the raw message is kept, folded
    assert "FileNotFoundError" not in text
    fold = alert.split('<details', 1)[1]
    assert '<span class="uk-fold-sum">Details</span>' in fold
    assert "<code>FileNotFoundError: the hub clone" in fold
    assert 'href="/data"' in alert


def test_an_unknown_scoring_failure_folds_its_message():
    html = _render(heads={}, us=None, us_row=None,
                   score_error="ValueError: boom")
    alert = html.split('id="rs-scorefail"', 1)[1].split("</span></div>", 1)[0]
    assert "ValueError" not in alert.split('<details', 1)[0]
    assert "<code>ValueError: boom</code>" in alert.split('<details', 1)[1]


def test_on_a_phone_the_failures_link_drops_under_its_text():
    css = (Path(__file__).resolve().parents[1] / "ui" / "static" / "tabs"
           / "retro.css").read_text(encoding="utf-8")
    assert ("@media (max-width:30rem){.rt-failalert > .uk-alert-text"
            "{flex-basis:calc(100% - 2rem)}}") in css
    assert 'cls="rt-failalert"' in SEASON_T
