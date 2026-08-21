"""Month-name time axes replace week-index axes on every swept surface.

An axis labeled "weeks since Aug 1" makes the reader do calendar
arithmetic. One server-side list of month-boundary week offsets
(SEASON_MONTHS in app/ui/server.py) now feeds every season-week axis:
the harmonic figure's ticks, the analogue mechanism diagram, and the
forecast data panel's season-over-season view; the retrospective's
cumulative relWIS chart derives its ticks from the same month table
through the date-indexed helper. The precise information moves to hover:
each season-over-season trace carries its own season's actual Saturday
date beside the value.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
DIAGRAMS_T = (UI / "templates" / "diagrams.html").read_text()
RETRO_SEASON_T = (UI / "templates" / "retro_season.html").read_text()


# ------------------------------------------------- the one shared offset list

def test_season_month_offsets_are_the_calendar():
    months = dict(srv.SEASON_MONTHS)
    assert [m for m, _ in srv.SEASON_MONTHS] == [
        "Aug", "Sep", "Oct", "Nov", "Dec", "Jan",
        "Feb", "Mar", "Apr", "May", "Jun", "Jul"]
    # spot values on the non-leap reference year, in weeks from August 1
    assert months["Aug"] == 0.0
    assert abs(months["Nov"] - 92 / 7) < 0.01
    assert abs(months["Feb"] - 184 / 7) < 0.01
    assert months["May"] == 39.0
    offs = [w for _, w in srv.SEASON_MONTHS]
    assert offs == sorted(offs) and offs[-1] < 52


def test_week_offsets_read_as_calendar_language():
    assert srv._season_week_name(22) == "early Jan"
    assert srv._season_week_name(20) == "mid Dec"
    assert srv._season_week_name(30) == "late Feb"
    assert srv._season_week_name(0) == "early Aug"


def test_every_consumer_reads_the_shared_list_not_a_copy():
    # forecast passes the server list into JS once; the analogue diagram
    # loops the template global; the harmonic ticks come from harmonic_fig,
    # which slices SEASON_MONTHS server-side; the cumulative chart calls the
    # date-indexed helper. No surface hand-types month offsets.
    assert "{{ season_months | tojson }}" in FORECAST_T
    assert "for lab, wk in season_months" in DIAGRAMS_T
    assert "month_ticks_for_dates" in RETRO_SEASON_T
    server_py = (UI / "server.py").read_text()
    assert server_py.count("_MONTH_DAYS = (") == 1
    assert "SEASON_MONTHS[::3]" in server_py       # harmonic_fig's source


# ------------------------------------------------------- swept surface: fig

def test_harmonic_ticks_are_months_at_month_start_positions():
    g = srv._harmonic_fig()
    assert [m for m, _ in g["ticks"]] == ["Aug", "Nov", "Feb", "May", "Aug"]
    xs = [x for _, x in g["ticks"]]
    assert xs == sorted(xs)
    assert xs[0] == 62.0 and xs[-1] == 540.0        # the axis span


# -------------------------------------------- swept surface: analogue diagram

def test_analogue_mechanism_axis_reads_as_months():
    html = srv.templates.env.get_template(
        "diagrams.html").module.analogue_mech()
    assert "weeks since August 1" not in html
    for m in ("Aug", "Nov", "Feb", "May", "Jul"):
        assert f">{m}</text>" in html, m
    # twelve ticks and twelve labels, all inside the 840-wide viewBox
    assert html.count(",255 v5") == 12
    assert 'y="277"' in html


# ------------------------------------------- swept surface: season over season

def test_forecast_season_over_season_uses_month_ticks_and_dated_hover():
    r = client.get("/forecast")
    assert r.status_code == 200
    # month ticks from the shared list, week-index title gone
    assert "SEASON_MONTHS.map(m=>m[1])" in r.text   # tickvals
    assert "SEASON_MONTHS.map(m=>m[0])" in r.text   # ticktext
    assert "weeks since Aug 1" not in r.text        # the axis title is gone
    # each trace hovers its own season's actual Saturday date plus the value
    assert "customdata:by[k].d" in r.text
    assert "%{customdata} · %{y:,.0f}" in r.text
    # the formatter never routes through Date (UTC parse shifts a day)
    assert "function fmtDate(ds){const p=ds.slice(0,10).split('-')" in r.text
    # the full-series view keeps its real-date axis: raw mode plots s.dates
    assert "{x:s.dates,y:s.values" in r.text


# --------------------------------------- swept surface: cumulative relWIS axis

def test_month_ticks_for_dates_marks_each_month_change():
    dates = ["2023-10-14", "2023-10-21", "2023-10-28", "2023-11-04",
             "2023-11-25", "2023-12-02", "2024-01-06"]
    assert srv._month_ticks_for_dates(dates) == [
        (3, "Nov"), (5, "Dec"), (6, "Jan")]
    assert srv._month_ticks_for_dates([]) == []
    assert srv._month_ticks_for_dates(["2024-05-04"]) == []


def test_cumulative_chart_draws_the_month_ticks():
    # the template loops the helper inside the chart svg, in the corner
    # dates' own muted style, between the plot band and the corner labels
    assert ("month_ticks_for_dates(curve | map('first') | list)"
            in RETRO_SEASON_T)
    for frag in ('y1="136"', 'y2="142"', 'y="154"'):
        assert RETRO_SEASON_T.count(frag) >= 1, frag
