"""Did every jurisdiction report the newest week? (app/core/reported.py)

The check reads the file a real-time run reads (observed_source), sorts
each gap as no row, blank value, a newest week reading 0 or a collapsed
one, and says what a run does with an unreported week by running the
Groundhog's own walk. Shown on the Data tab's hub card, in the Update data
message, and under the Forecast tab's anchor line, where the zeros and
collapses get the Data issues box. Hub-free: each test builds a tiny hub
in tmp_path.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.core.data as data                                 # noqa: E402
from app.core import reported                                # noqa: E402
from app.core.engines import analogue as AE                  # noqa: E402
from app.ui import server as srv                             # noqa: E402
from app.ui import shared as ui_shared                       # noqa: E402
from app.ui import state as ui_state                         # noqa: E402
from app.ui.routes import data as ui_data                    # noqa: E402

client = TestClient(srv.app)

#: Saturdays, oldest first; the last is the newest week
WEEKS = ["2098-09-06", "2098-09-13", "2098-09-20", "2098-09-27",
         "2098-10-04", "2098-10-11"]
NEW = WEEKS[-1]
LOCS = [("US", "US"), ("31", "Nebraska"), ("39", "Ohio"), ("49", "Utah"),
        ("56", "Wyoming")]


def _hub(root: Path, monkeypatch, newest=None, drop_weeks=None,
         vintages=()):
    """A hub whose live file holds WEEKS for LOCS at 40 admissions a week;
    `newest` overrides a location's newest-week cell ({name: "" | "0" |
    None (no row)}) and `drop_weeks` removes a location's older rows."""
    newest = newest or {}
    drop_weeks = drop_weeks or {}
    (root / "target-data").mkdir(parents=True, exist_ok=True)
    arch = root / "auxiliary-data" / "target-data-archive"
    arch.mkdir(parents=True, exist_ok=True)
    (root / "auxiliary-data" / "locations.csv").write_text(
        "location,location_name\n"
        + "".join(f"{f},{n}\n" for f, n in LOCS))
    rows = ["date,location,location_name,value,weekly_rate"]
    for w in WEEKS:
        for f, n in LOCS:
            if w in drop_weeks.get(n, ()):
                continue
            v = "40"
            if w == NEW and n in newest:
                if newest[n] is None:
                    continue
                v = newest[n]
            rows.append(f"{w},{f},{n},{v},1.0")
    (root / data.LIVE_TARGET).write_text("\n".join(rows) + "\n")
    for v in vintages:
        (arch / f"target-hospital-admissions_{v}.csv").write_text(
            "\n".join(r for r in rows if r[:10] <= v or r[0] == "d") + "\n")
    monkeypatch.setattr(data, "HUB", root)
    monkeypatch.setattr(data, "ARCHIVE", arch)
    monkeypatch.setattr(AE, "LOCATIONS", root / "auxiliary-data" / "locations.csv")
    ui_shared._invalidate_scans()
    return root


@pytest.fixture(autouse=True)
def _isolated():
    status_before, form_before = dict(ui_state._status), dict(ui_state._last_form)
    yield
    ui_state._status.clear(); ui_state._status.update(status_before)
    ui_state._last_form.clear(); ui_state._last_form.update(form_before)
    ui_shared._invalidate_scans()


# --- the completeness function ------------------------------------------------

def test_every_location_reported(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch)
    r = reported.check()
    assert r.complete and r.kind == "live" and r.week == NEW
    assert r.expected == len(LOCS)
    assert r.line() == f"All {len(LOCS)} jurisdictions reported for week {NEW}"
    assert r.short() == f"All {len(LOCS)} reported"


def test_no_row_and_blank_are_told_apart_and_forecast_from_the_week_before(
        tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch,
         newest={"Nebraska": None, "Utah": ""})
    r = reported.check()
    got = {g.location: (g.reason, g.action, g.from_week) for g in r.gaps}
    assert got == {"Nebraska": ("no row", "forecast", WEEKS[-2]),
                   "Utah": ("blank", "forecast", WEEKS[-2])}
    # the line counts; the names are in the tip (details)
    assert r.line() == f"3 of {len(LOCS)} reported · 2 not reported"
    assert r.short() == f"3 of {len(LOCS)} reported · 2 not reported"
    assert r.details()[:2] == [
        f"No row: Nebraska. Forecast from {WEEKS[-2]}.",
        f"Blank value: Utah. Forecast from {WEEKS[-2]}."]
    assert r.details()[2].startswith("Each is chosen per state in Data issues")


def test_a_location_beyond_the_anchor_lag_is_skipped(tmp_path, monkeypatch):
    # Wyoming's newest reported week is MAX_ANCHOR_LAG + 1 weeks unreported
    gone = WEEKS[-(AE.MAX_ANCHOR_LAG + 1):]
    _hub(tmp_path / "hub", monkeypatch, drop_weeks={"Wyoming": gone})
    r = reported.check()
    (g,) = r.gaps
    assert (g.location, g.reason, g.action) == ("Wyoming", "no row", "skip")
    last = WEEKS[-(AE.MAX_ANCHOR_LAG + 2)]
    assert last in g.why and f"more than {AE.MAX_ANCHOR_LAG} unreported" in g.why
    assert r.line() == f"4 of {len(LOCS)} reported · 1 not reported"
    assert r.details()[0].startswith("No row: Wyoming. Skipped: its newest")
    assert reported.recommend(g) == ("carry", g.why)
    # at exactly MAX_ANCHOR_LAG unreported weeks it still forecasts
    _hub(tmp_path / "hub2", monkeypatch,
         drop_weeks={"Wyoming": WEEKS[-AE.MAX_ANCHOR_LAG:]})
    (g,) = reported.check().gaps
    assert (g.action, g.from_week) == ("forecast",
                                       WEEKS[-(AE.MAX_ANCHOR_LAG + 1)])


def test_a_zero_is_flagged_and_worded_by_consequence(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    r = reported.check()
    (g,) = r.gaps
    assert (g.location, g.reason, g.prev) == ("Ohio", "zero", 40.0)
    assert g.action == "no_groundhog"
    # the week is complete (every jurisdiction has a value), not clean
    assert r.complete and not r.clean
    assert g.what() == "reads 0 after 40, 40, 40"
    assert g.flag() == "0 after 40, 40, 40"
    assert r.line() == f"All {len(LOCS)} reported · 1 reads 0"
    assert r.short() == f"All {len(LOCS)} reported · 1 reads 0"
    assert r.details()[0] == ("0 after 40, 40, 40: Ohio. Recommended: set "
                              "aside (looks like a missed report).")
    assert reported.ZERO_FACT in r.details()
    # the setting treats it as missing: the run forecasts from the week before
    (g,) = reported.check("missing").gaps
    assert (g.action, g.from_week) == ("forecast", WEEKS[-2])


def test_a_zero_after_small_weeks_is_flagged_too_and_worded_so(
        tmp_path, monkeypatch):
    root = _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    live = root / data.LIVE_TARGET
    text = live.read_text()
    for w, v in zip(WEEKS[-4:-1], ("1", "4", "2")):
        text = text.replace(f"{w},39,Ohio,40", f"{w},39,Ohio,{v}")
    live.write_text(text)
    r = reported.check()
    (g,) = r.gaps
    assert g.reason == "zero" and g.what() == "reads 0, recent weeks 1-4"
    assert g.flag() == "0 after 2, 4, 1"
    assert g.zeros == 1 and g.can_set_aside
    assert g.aside == [(NEW, 0.0)] and g.last_positive == (WEEKS[-2], 2.0)
    assert reported.recommend(g) == ("level", "small counts; level scored best on such weeks")
    # a longer run of zeros names the last positive week; no set-aside
    text = text.replace(f"{WEEKS[-2]},39,Ohio,2", f"{WEEKS[-2]},39,Ohio,0")
    text = text.replace(f"{WEEKS[-3]},39,Ohio,4", f"{WEEKS[-3]},39,Ohio,0")
    live.write_text(text)
    (g,) = reported.check().gaps
    assert g.what() == f"reads 0 for 3 weeks (last 1 on {WEEKS[-4]})"
    assert g.flag() == "0 for 3 wk"
    assert g.zeros == 3 and not g.can_set_aside
    assert reported.recommend(g) == ("level", "0 for 3 weeks; level falls back to a Poisson floor")


def test_a_collapsed_week_is_flagged(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "5"})
    r = reported.check()
    (g,) = r.gaps
    assert (g.location, g.reason, g.prev) == ("Ohio", "collapsed", 40.0)
    assert g.what() == "reads 5 after 40" and g.can_set_aside
    assert g.flag() == "5 after 40"
    assert r.complete and not r.clean
    assert r.line() == f"All {len(LOCS)} reported · 1 collapsed"
    assert r.short() == f"All {len(LOCS)} reported · 1 collapsed"
    assert r.details()[0] == ("5 after 40: Ohio. Recommended: set aside "
                              "(looks like a partial report).")
    assert reported.COLLAPSED_FACT in r.details()
    # a moderate drop is not a collapse (a fifth of the week before)
    _hub(tmp_path / "hub2", monkeypatch, newest={"Ohio": "8"})
    assert reported.check().clean


def test_the_box_rows_offer_each_state_its_choices(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch,
         newest={"Ohio": "0", "Utah": "5", "Nebraska": None})
    rows = {r["name"]: r for r in reported.box_rows(reported.check())}
    ohio = rows["Ohio"]
    assert ohio["issue"] == "zero" and ohio["default"] == ""
    assert [v for v, _ in ohio["options"]] == list(reported.MS.ZERO_CHOICES)
    labels = dict(ohio["options"])
    md = WEEKS[-2][5:]                              # MM-DD
    assert labels == {"abstain": "No forecast", "level": "Level (mean of 4 wk)",
                      "extend": f"Extend 40 from {md}", "blend": "Blend",
                      "set_aside": f"Both from {md}", "omit": "Leave out"}
    assert ohio["aside"] == [[NEW, 0.0]]
    assert ohio["flag"] == "0 after 40, 40, 40"
    assert (ohio["rec"], ohio["why"]) == (
        "set_aside", "0 after 40, 40, 40 looks like a missed report")
    assert ohio["hint"] == ohio["why"]
    utah = rows["Utah"]
    assert utah["issue"] == "collapsed" and utah["default"] == "keep"
    assert utah["options"] == [("keep", "Keep 5"), ("set_aside", f"Both from {md}"),
                               ("omit", "Leave out")]
    assert utah["rec"] == "set_aside" and utah["flag"] == "5 after 40"
    neb = rows["Nebraska"]
    assert neb["issue"] == "no row" and neb["default"] == "carry"
    assert neb["options"] == [("carry", f"From {md}"), ("omit", "Leave out")]
    assert neb["rec"] == "carry" and neb["flag"] == "no row"
    assert neb["hint"] == f"forecast from {WEEKS[-2]}"


def _gap(reason, values, **kw):
    weeks = WEEKS[-len(values):]
    prev = values[-2] if len(values) >= 2 else None
    return reported.Gap("Ohio", reason, "39", prev=prev,
                        reported=list(zip(weeks, map(float, values))), **kw)


def test_the_recommendation_rule_branch_by_branch():
    rec = reported.recommend
    # a 0 after a week of ZERO_FLOOR or more: a missed report is likely
    assert rec(_gap("zero", [3, 24, 19, 0])) == (
        "set_aside", "0 after 19, 24, 3 looks like a missed report")
    assert rec(_gap("zero", [3, 24, 19, 0, 0])) == (
        "set_aside", "0, 0 after 19, 24 looks like a missed report")
    assert rec(_gap("zero", [1, 10, 0]))[0] == "set_aside"     # at the floor
    assert rec(_gap("zero", [1, 9, 0]))[0] == "level"          # under it
    # small counts: level scored best
    assert rec(_gap("zero", [1, 4, 2, 0])) == (
        "level", "small counts; level scored best on such weeks")
    assert rec(_gap("zero", [40, 1, 4, 2, 0])) == (      # only the 3 prior weeks count
        "level", "small counts; level scored best on such weeks")
    # a run of 3 or more (past MAX_CARRY): level, its Poisson floor
    assert rec(_gap("zero", [5, 6, 0, 0, 0])) == (
        "level", "0 for 3 weeks; level falls back to a Poisson floor")
    assert rec(_gap("zero", [0, 0])) == (
        "level", "0 for 2 weeks; level falls back to a Poisson floor")
    # a collapse: a partial report, unless the two weeks before already
    # fell by more than half each (a real drop)
    assert rec(_gap("collapsed", [190, 200, 194, 8])) == (
        "set_aside", "8 after 194 looks like a partial report")
    assert rec(_gap("collapsed", [100, 49, 24, 4])) == (
        "keep", "falling for 2 weeks; the drop may be real")
    assert rec(_gap("collapsed", [100, 80, 52, 9]))[0] == "set_aside"
    assert rec(_gap("collapsed", [49, 24, 4]))[0] == "set_aside"   # one fall known
    # not reported: the engines' own walk
    assert rec(_gap("no row", [40, 40], action="forecast", from_week=WEEKS[-2])) == (
        "carry", f"forecast from {WEEKS[-2]}")
    assert rec(_gap("blank", [40, 40], action="skip", why="no reported week in the data")) == (
        "carry", "no reported week in the data")


def test_the_check_reads_the_file_a_real_time_run_reads(tmp_path, monkeypatch):
    # the archive holds the newest week complete; the live file lacks Utah:
    # a real-time run reads the live file, so the check does too
    root = _hub(tmp_path / "hub", monkeypatch, vintages=[NEW])
    live = root / data.LIVE_TARGET
    live.write_text("\n".join(l for l in live.read_text().splitlines()
                              if not l.startswith(f"{NEW},49,")) + "\n")
    assert data.observed_source(NEW, "realtime")[1] == "live"
    r = reported.check()
    assert r.kind == "live" and [g.location for g in r.gaps] == ["Utah"]


def test_no_hub_data_gives_no_report(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "HUB", tmp_path / "none")
    monkeypatch.setattr(data, "ARCHIVE", tmp_path / "none" / "a")
    assert reported.check() is None


def test_the_line_counts_and_the_tip_names_every_location(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch,
         newest={"Nebraska": None, "Ohio": None, "Utah": "0", "Wyoming": "5"})
    r = reported.check()
    assert r.line() == (f"3 of {len(LOCS)} reported · 2 not reported "
                        "· 1 reads 0 · 1 collapsed")
    assert r.details()[0] == f"No row: Nebraska, Ohio. Forecast from {WEEKS[-2]}."
    assert "Ohio" not in r.line() and "Nebraska" not in r.line()


# --- the three places ---------------------------------------------------------

def test_data_tab_card_shows_the_check(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch)
    page = client.get("/data").text
    assert 'id="newest-check"' in page
    assert 'class="ncmark ok" role="img" aria-label="Complete"' in page
    assert f"All {len(LOCS)} jurisdictions reported for week {NEW}" in page
    _hub(tmp_path / "hub2", monkeypatch, newest={"Nebraska": None})
    page = client.get("/data").text
    assert 'aria-label="Incomplete"' in page
    # the grid row: the pill carries the count, the text the head
    assert '<span class="pill warn">1 not reported</span>' in page
    assert f"4 of {len(LOCS)} reported" in page
    assert f"No row: Nebraska. Forecast from {WEEKS[-2]}." in page


def test_update_data_message_carries_the_check(tmp_path, monkeypatch):
    root = _hub(tmp_path / "hub", monkeypatch)

    def pull():                          # the new week arrives without Utah
        live = root / data.LIVE_TARGET
        live.write_text("\n".join(
            l for l in live.read_text().splitlines()
            if not l.startswith(f"{NEW},49,")) + "\n")
        return True, "Fast-forward"
    monkeypatch.setattr(data, "pull_hub", pull)
    ui_state._status.pop("flash", None)
    client.post("/data/pull", follow_redirects=False)
    flash = ui_state._status.get("flash") or ""
    # one short clause, a count: the Data tab's card names the states
    assert flash == f"Up to date · data through {NEW} · 1 state not reported"
    assert "Utah" not in flash
    # a newest week reading 0 is one clause too, again a count
    ui_state._status.pop("flash", None)
    root = _hub(tmp_path / "hub2", monkeypatch, newest={"Ohio": "0"})
    for _n, sub in data.COMPARATORS:         # a missing comparator would lead
        (root / sub).mkdir(parents=True)
    monkeypatch.setattr(data, "pull_hub", lambda: (True, "Already up to date."))
    client.post("/data/pull", follow_redirects=False)
    flash = ui_state._status.get("flash") or ""
    assert flash == f"Up to date · data through {NEW} · 1 state reads 0"
    # the card still names them, with the pointer
    page = client.get("/data").text
    assert '<span class="pill warn">1 read 0</span>' in page
    assert "Ohio" in page


def test_forecast_tab_line_under_the_anchor(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Utah": ""})
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": NEW, "locations": ["all"],
                                "engine": "all"})
    page = client.get("/forecast").text
    anchor = page.index('id="anchor-line"')
    check = page.index('id="newest-check"')
    assert anchor < check and page.index('id="vintage-pick"') > check
    tag = page[page.rindex("<p", 0, check):page.index(">", check)]
    assert "hidden" not in tag and f'data-week="{NEW}"' in tag
    assert f"{len(LOCS) - 1} of {len(LOCS)} reported" in page
    assert 'aria-label="Incomplete"' in page
    # an older anchor week: the line is there for the script, hidden
    ui_state._last_form.update({"forecast_date": WEEKS[-3]})
    page = client.get("/forecast").text
    check = page.index('id="newest-check"')
    assert " hidden" in page[page.rindex("<p", 0, check):page.index(">", check)]
    # the script follows the date
    assert "nc.hidden = a !== nc.dataset.week" in page


def test_forecast_tab_says_all_reported_in_green(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch)
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": NEW, "locations": ["all"],
                                "engine": "all"})
    page = client.get("/forecast").text
    assert 'class="newest-check hint ok"' in page
    assert f"All {len(LOCS)} reported" in page


def test_forecast_setting_reaches_the_check(tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    ui_state._last_form.clear()
    ui_state._last_form.update({"forecast_date": NEW, "locations": ["all"],
                                "engine": "all",
                                "knobs": {"data.trailing_zero": "missing"}})
    (g,) = ui_data._newest_report().gaps
    assert (g.action, g.from_week) == ("forecast", WEEKS[-2])
    page = client.get("/forecast").text
    assert f"All {len(LOCS)} reported · 1 reads 0" in page
    assert 'aria-label="Complete, with issues"' in page
    assert "0 after 40, 40, 40: Ohio. Recommended: set aside" in page
