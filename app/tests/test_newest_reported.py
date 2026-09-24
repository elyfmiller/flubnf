"""Did every jurisdiction report the newest week? (app/core/reported.py)

The check reads the file a real-time run reads (observed_source), sorts
each gap as no row, blank value, or a 0 after a week of 10 or more, and
says what a run does with it by running the Groundhog's own walk. Shown on
the Data tab's hub card, in the Update data message, and under the Forecast
tab's anchor line. Hub-free: each test builds a tiny hub in tmp_path.
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
    assert r.line() == (f"2 jurisdictions not reported for {NEW}: "
                        f"Nebraska, Utah (forecast from {WEEKS[-2]})")
    assert r.details() == [
        f"No row: Nebraska. Forecast from {WEEKS[-2]}.",
        f"Blank value: Utah. Forecast from {WEEKS[-2]}."]


def test_a_location_beyond_the_anchor_lag_is_skipped(tmp_path, monkeypatch):
    # Wyoming's newest reported week is MAX_ANCHOR_LAG + 1 weeks unreported
    gone = WEEKS[-(AE.MAX_ANCHOR_LAG + 1):]
    _hub(tmp_path / "hub", monkeypatch, drop_weeks={"Wyoming": gone})
    r = reported.check()
    (g,) = r.gaps
    assert (g.location, g.reason, g.action) == ("Wyoming", "no row", "skip")
    last = WEEKS[-(AE.MAX_ANCHOR_LAG + 2)]
    assert last in g.why and f"more than {AE.MAX_ANCHOR_LAG} unreported" in g.why
    assert r.line().endswith("Wyoming (skipped)")
    # at exactly MAX_ANCHOR_LAG unreported weeks it still forecasts
    _hub(tmp_path / "hub2", monkeypatch,
         drop_weeks={"Wyoming": WEEKS[-AE.MAX_ANCHOR_LAG:]})
    (g,) = reported.check().gaps
    assert (g.action, g.from_week) == ("forecast",
                                       WEEKS[-(AE.MAX_ANCHOR_LAG + 1)])


def test_a_zero_after_ten_or_more_is_flagged_and_follows_the_setting(
        tmp_path, monkeypatch):
    _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    r = reported.check()
    (g,) = r.gaps
    assert (g.location, g.reason, g.prev) == ("Ohio", "zero", 40.0)
    assert g.action == "no_groundhog"
    assert r.line() == (f"1 jurisdiction reads 0 for {NEW}: Ohio "
                        "(no Groundhog forecast)")
    assert "Newest weeks reading 0" in r.details()[0]
    # the setting treats it as missing: the run forecasts from the week before
    (g,) = reported.check("missing").gaps
    assert (g.action, g.from_week) == ("forecast", WEEKS[-2])


def test_a_zero_after_a_small_week_is_a_real_count(tmp_path, monkeypatch):
    root = _hub(tmp_path / "hub", monkeypatch, newest={"Ohio": "0"})
    live = root / data.LIVE_TARGET
    small = str(reported.MS.ZERO_FLOOR - 1).rstrip("0").rstrip(".")
    live.write_text(live.read_text().replace(
        f"{WEEKS[-2]},39,Ohio,40", f"{WEEKS[-2]},39,Ohio,{small}"))
    assert reported.check().complete


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


def test_a_long_list_is_cut_to_a_short_line(tmp_path, monkeypatch):
    monkeypatch.setattr(reported, "LINE_NAMES", 2)
    _hub(tmp_path / "hub", monkeypatch,
         newest={"Nebraska": None, "Ohio": None, "Utah": None})
    assert "Nebraska, Ohio and 1 more" in reported.check().line()


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
    assert (f"1 jurisdiction not reported for {NEW}: Nebraska "
            f"(forecast from {WEEKS[-2]})") in page
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
    assert (f"1 jurisdiction not reported for {NEW}: Utah "
            f"(forecast from {WEEKS[-2]})") in flash


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
    assert f"1 jurisdiction not reported for {NEW}: Utah" in page
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
    page = client.get("/forecast").text
    assert f"(forecast from {WEEKS[-2]})" in page
