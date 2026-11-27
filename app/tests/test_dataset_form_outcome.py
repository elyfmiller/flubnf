"""What a dataset's check and Forecast form say before anything runs (the
2026-11-27 user review: B5, B13, B15).

  * the check's preview leads with what storing the file leads to: which
    models can forecast it, or that none can yet and what would fix it
    (datasets_ui.outcome_line), never "Ready to use" over a file nothing
    can forecast;
  * a newest week that ends after today may still be filling in: the
    Forecast form says so while the date anchors on it, and offers the
    week before it (datasets_ui.future_week);
  * what a past week sees (the snapshot that held it, or today's numbers)
    is said in Vintage mode only, in plain words, not as a warning badge
    beside every dataset.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from html import unescape
from pathlib import Path

from app.ui import datasets_ui as DU

from test_datasets_ui import client, isolated, stored  # noqa: E402,F401

ROOT = Path(__file__).resolve().parents[2]
G, F = DU.GROUNDHOG, DU.FILTER


# ------------------------------------------------------------ the outcome

def test_the_outcome_names_what_can_forecast_and_the_fix_when_nothing_can():
    ok, warn = ("ok", "ready"), ("warn", "too little history")
    some = ("warn", "some horizons only")
    pop = ("warn", "needs a population")
    rates = ("neutral", "counts only")
    fix = "Give about 2 more earlier seasons of data."
    assert DU.outcome_line([(G, *ok), (F, *ok)]) == (
        "ok", f"Can forecast with {G} and {F}.")
    assert DU.outcome_line([(G, *ok), (F, *pop)], fix) == (
        "ok", f"Can forecast with {G}.")
    assert DU.outcome_line([(G, *some), (F, *ok)]) == (
        "ok", f"Can forecast with {F}. {G} can forecast some horizons only.")
    assert DU.outcome_line([(G, *some), (F, *rates)], fix) == (
        "warn", f"Can forecast some horizons only, with {G}. {fix}")
    assert DU.outcome_line([(G, *warn), (F, *pop)], fix) == (
        "warn", f"Can't forecast yet. {fix}")
    assert DU.outcome_line([(G, *warn), (F, *rates)]) == (
        "warn", "Can't forecast yet.")


# ------------------------------------------------- a week ending after today

def test_future_week_is_the_newest_week_only_when_it_ends_after_today():
    today = date(2026, 11, 27)
    weeks = ["2026-11-14", "2026-11-21", "2026-11-28"]
    assert DU.future_week(weeks, today) == {"week": "2026-11-28",
                                            "before": "2026-11-21"}
    assert DU.future_week(weeks[:2], today) is None
    assert DU.future_week(["2026-11-28"], today) == {"week": "2026-11-28",
                                                     "before": ""}
    assert DU.future_week([], today) is None
    # the day itself has come: not ahead
    assert DU.future_week(weeks, date(2026, 11, 28)) is None
    # two weeks ahead: the offer is the newest week that has ended
    assert DU.future_week(weeks + ["2026-12-05"], today) == {
        "week": "2026-12-05", "before": "2026-11-21"}
    assert DU.future_week(["2026-11-28", "2026-12-05"], today) == {
        "week": "2026-12-05", "before": ""}


def _weekly(last: date, n: int = 40) -> bytes:
    lines = ["date,group,value"]
    for i in range(n):
        d = last - timedelta(days=7 * (n - 1 - i))
        lines.append(f"{d.isoformat()},A,{10 + i % 7}")
    return ("\n".join(lines) + "\n").encode()


def test_the_form_says_when_the_newest_week_ends_after_today():
    today = date.today()
    ahead = today + timedelta(days=(5 - today.weekday()) % 7 or 7)
    ds = stored(_weekly(ahead), "Ahead")
    newest, before = ds.forecast_dates()[-1], ds.forecast_dates()[-2]
    assert newest == ahead.isoformat()
    page = unescape(client.get(f"/forecast?source={ds.id}").text)
    note = page[page.index('id="fc-future"'):]
    note = note[:note.index("</div>")]
    assert (f"The newest week ends {newest}, after today, so it may be "
            "incomplete.") in note
    assert "hidden" not in note.split(">", 1)[0]        # the date is on it
    link = f'href="/forecast?source={ds.id}&forecast_date={before}"'
    assert link in note and f"Forecast from {before}" in note
    # the link opens the form on that week (the page starts in Vintage
    # mode for a date before the newest)
    again = client.get(f"/forecast?source={ds.id}&forecast_date={before}")
    assert f'name="forecast_date" value="{before}"' in again.text
    # a week the dataset does not hold is ignored
    odd = client.get(f"/forecast?source={ds.id}&forecast_date=1999-01-02")
    assert f'name="forecast_date" value="{newest}"' in odd.text
    # a dataset whose newest week has passed says nothing
    past = stored(_weekly(ahead - timedelta(days=14)), "Past")
    assert 'id="fc-future"' not in client.get(
        f"/forecast?source={past.id}").text


# ------------------------------------------------------ what a past week sees

def test_what_a_past_week_sees_is_said_outside_real_time():
    ds = stored()
    page = unescape(client.get(f"/forecast?source={ds.id}").text)
    assert 'id="fc-ds-truth"' not in page
    assert "final data, not vintage-true" not in page
    m = re.search(r'<p class="fc-pastnote" id="fc-pastnote">(.*?)</p>', page,
                  re.S)
    text = " ".join(re.sub(r"<[^>]+>", " ", m.group(1)).split())
    assert text == ("Past weeks use the data as it was reported then."
                    if ds.vintage_true else
                    "Past weeks use today's numbers, not what was known then.")
    css = (ROOT / "app/ui/static/tabs/forecast.css").read_text(
        encoding="utf-8")
    # hidden in Real-time only: shown in Vintage and without script, where
    # the server runs whatever week is typed
    assert "#fcform.mode-realtime .fc-pastnote{display:none}" in css
    assert ":not(.mode-vintage) .fc-pastnote" not in css
    # inside the form, so the mode's class on it reaches the line
    assert page.index('id="fcform"') < page.index('id="fc-pastnote"')


# ------------------------------------------- the group pickers' filters

def test_enter_in_a_group_filter_never_submits_the_form():
    """Enter applies a search box's filter; in the replay form it once
    pressed Replay (the form's first submit button)."""
    ds = stored()
    for url, fid in ((f"/retro?dataset={ds.id}", "filt"),
                     (f"/forecast?source={ds.id}", "FILTER")):
        page = client.get(url).text
        assert (f"{fid}.addEventListener('keydown', function (e) {{"
                in page), url
        assert "if (e.key === 'Enter') e.preventDefault();" in page, url


def test_no_group_ticked_says_every_group_replays():
    ds = stored()
    page = client.get(f"/retro?dataset={ds.id}").text
    assert "'none ticked: all ' + ones.length + ' replay'" in page
    # the replay form's own Use and the Replay that waits for it
    form = page[page.index('id="dsr-srcform"'):]
    assert '<button class="quiet">Use</button>' in form[:form.index("</form>")]
    assert 'id="dsr-run" data-guard="console-run">Replay</button>' in page
    assert "Replay is off: press Use to open " in page
