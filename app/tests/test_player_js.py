"""The shared season player (app/ui/static/player.js).

Two layers: the pure view-state and availability logic runs for real under
JavaScriptCore (jsc ships with macOS; the tests skip cleanly where it is
absent), and source-level checks pin the properties both hosts depend on
(Safari safety, no network calls of its own, the availability rendering,
and the view-state clear sites)."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

PLAYER = Path(__file__).resolve().parents[1] / "ui" / "static" / "player.js"
SRC = PLAYER.read_text(encoding="utf-8")
JSC = Path("/System/Library/Frameworks/JavaScriptCore.framework/"
           "Versions/Current/Helpers/jsc")
needs_jsc = pytest.mark.skipif(not JSC.is_file(),
                               reason="JavaScriptCore jsc not available")


def _js(tmp_path, expr):
    """Evaluate one expression against the player's exported internals."""
    drv = tmp_path / "driver.js"
    drv.write_text(
        "var I = FluBNFPlayer._internals;\n"
        "print(JSON.stringify((function(){ return " + expr + "; })()));\n")
    out = subprocess.run([str(JSC), str(PLAYER), str(drv)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, (out.stderr or out.stdout)
    return json.loads(out.stdout.strip().splitlines()[-1])


# ------------------------------------------------- view-state logic (fix 1)

@needs_jsc
def test_zoom_event_becomes_active_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: null, y: null},"
              " {'xaxis.range[0]': '2098-10-01',"
              "  'xaxis.range[1]': '2098-12-01',"
              "  'yaxis.range[0]': 0, 'yaxis.range[1]': 500})")
    assert got == {"x": ["2098-10-01", "2098-12-01"], "y": [0, 500]}


@needs_jsc
def test_single_axis_pan_merges_with_stored_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: null, y: [0, 5]},"
              " {'xaxis.range[0]': 1, 'xaxis.range[1]': 2})")
    assert got == {"x": [1, 2], "y": [0, 5]}


@needs_jsc
def test_autorange_reset_clears_view(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: [1, 2], y: [0, 5]},"
              " {'xaxis.autorange': true})")
    assert got == {"x": None, "y": None}


@needs_jsc
def test_unrelated_relayout_leaves_view_untouched(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate({x: [1, 2], y: null},"
              " {dragmode: 'pan'})")
    assert got == {"x": [1, 2], "y": None}


@needs_jsc
def test_array_form_range_accepted(tmp_path):
    got = _js(tmp_path,
              "I.viewStateUpdate(null, {'xaxis.range': [3, 4]})")
    assert got == {"x": [3, 4], "y": None}


# --------------------------------------- per-model availability (fix 2)

@needs_jsc
def test_official_availability_is_per_model(tmp_path):
    # the real case: the baseline directory healed before the ensemble
    # directory joined the sparse set, so only one official is present
    got = _js(tmp_path,
              "I.officialAvailability("
              "{official: {'FluSight-baseline': {US: {}}}}, I.OFFICIALS)")
    assert got == {"FluSight-baseline": True, "FluSight-ensemble": False}


@needs_jsc
def test_official_availability_empty_payload(tmp_path):
    got = _js(tmp_path, "I.officialAvailability(null, I.OFFICIALS)")
    assert got == {"FluSight-baseline": False, "FluSight-ensemble": False}


# ------------------------------------------ two-tier availability (fix 2)

@needs_jsc
def test_availability_tier_three_states(tmp_path):
    got = _js(tmp_path, "[I.availabilityTier(true, true),"
                        " I.availabilityTier(false, true),"
                        " I.availabilityTier(false, false)]")
    assert got == [
        # present this week: enabled, no note
        {"disabled": False, "note": ""},
        # in-season gap (outside the competition window): the toggle stays
        # live; the transient note explains the empty frame
        {"disabled": False, "note": " (no official submission this week)"},
        # absent all season: the existing disabled + Update-data state
        {"disabled": True, "note": " (fetch via Update data on the Data tab)"},
    ]


@needs_jsc
def test_availability_tier_week_presence_wins(tmp_path):
    # a week-present model is enabled regardless of the season flag (the
    # degenerate true/false combination cannot arise, but must not disable)
    got = _js(tmp_path, "I.availabilityTier(true, false)")
    assert got == {"disabled": False, "note": ""}


# ------------------------------ week-cell reading: pending vs no submission

@needs_jsc
def test_week_cell_score_always_wins(tmp_path):
    # a real number is rendered as a score no matter what the availability
    # flags say (officials included)
    got = _js(tmp_path, "[I.weekCellState(0.9, false, true, false, false),"
                        " I.weekCellState(1.2, true, true, false, true)]")
    assert got == ["score", "score"]


@needs_jsc
def test_week_cell_cataloged_official_without_a_file_reads_no_submission(
        tmp_path):
    # season-cataloged, no file for THIS week: it did not compete, which is
    # not the same as an uncomputed score
    got = _js(tmp_path, "I.weekCellState(null, true, true, false, true)")
    assert got == "nosub"


@needs_jsc
def test_week_cell_pending_cases(tmp_path):
    # every remaining blank is a genuinely uncomputed score:
    #   our own member with no score yet;
    #   an official present this week but unscored;
    #   an official absent all season (the disabled-toggle case);
    #   a week whose payload never arrived, where nothing is known about
    #   who submitted, so no no-submission claim may be made
    got = _js(tmp_path, "[I.weekCellState(null, false, true, false, false),"
                        " I.weekCellState(null, true, true, true, true),"
                        " I.weekCellState(null, true, true, false, false),"
                        " I.weekCellState(null, true, false, false, true)]")
    assert got == ["pending", "pending", "pending", "pending"]


@needs_jsc
def test_add_days_utc(tmp_path):
    assert _js(tmp_path, "I.addDays('2098-12-02', 28)") == "2098-12-30"


# --------------------------------------------- no-forecast frames (class fix)

@needs_jsc
def test_no_forecast_note_states_the_empty_us_frame(tmp_path):
    # a US frame outside the officials' competition window has nothing to
    # draw; the caption states the structural reason instead of standing
    # as bare axes (field-found on the 2025-26 season player)
    got = _js(tmp_path, "I.noForecastNote('US', 0, 0)")
    assert "no official US submission" in got
    assert "per state" in got


@needs_jsc
def test_no_forecast_note_states_a_bare_state_frame(tmp_path):
    got = _js(tmp_path, "I.noForecastNote('Ohio', 0, 0)")
    assert got == "no forecast for Ohio this week"


@needs_jsc
def test_no_forecast_note_distinguishes_toggled_off_from_absent(tmp_path):
    # data present with every model toggled off is the viewer's own state
    got = _js(tmp_path, "[I.noForecastNote('Ohio', 2, 0),"
                        " I.noForecastNote('US', 1, 0)]")
    assert got == ["no models enabled", "no models enabled"]


@needs_jsc
def test_no_forecast_note_silent_when_fans_draw(tmp_path):
    got = _js(tmp_path, "[I.noForecastNote('Ohio', 2, 2),"
                        " I.noForecastNote('US', 1, 1)]")
    assert got == ["", ""]


# ------------------------------------------------------- source guarantees

def test_safari_safe_and_host_agnostic():
    # Safari-safe: no lookbehind regexes, nothing async at the top level
    assert "(?<=" not in SRC and "(?<!" not in SRC
    assert not re.search(r"\basync\b|\bawait\b", SRC)
    # host-agnostic: the player never touches the network itself, and it
    # embeds cleanly in the self-contained report (whose test forbids
    # these substrings anywhere in the built file)
    assert "fetch(" not in SRC
    assert "/static/" not in SRC
    assert "</script" not in SRC.lower()
    assert "http://" not in SRC and "https://" not in SRC
    assert "@@" not in SRC       # would collide with the report's tokens


def test_marker_and_exports():
    assert "flubnf-player-v1" in SRC
    assert "root.FluBNFPlayer = FluBNFPlayer" in SRC


def test_availability_rendering_wired():
    # every model toggle carries an availability note span, refreshed on
    # every payload through the two-tier verdict: week-absent but
    # season-present stays enabled with the transient note, whole-season
    # absent keeps the disabled + Update-data state
    assert "data-avail" in SRC
    assert "(fetch via Update data on the Data tab)" in SRC
    assert "(no official submission this week)" in SRC
    assert "availabilityTier(av[m], !!seasonOffs[m])" in SRC
    assert "box.disabled = tier.disabled" in SRC
    assert "officialAvailability(pl, OFFS)" in SRC
    assert "updateAvailability(pl)" in SRC
    # the user's checked state is never touched by availability updates
    assert "box.checked" not in SRC
    # season availability: host-provided (seasonOfficials, or the static
    # host's catalog union) and grown from every payload seen
    assert "cfg.seasonOfficials || (cfg.catalog && cfg.catalog.officials)" \
        in SRC
    assert "seasonOffs[m] = 1" in SRC


def test_stats_table_distinguishes_no_submission_from_pending():
    # the week cell carries both readings, muted; the cumulative cell is
    # rendered by fmt alone, so a cataloged official keeps its real running
    # number through a week it skipped
    assert '<td class="num hint">no submission</td>' in SRC
    assert '<td class="num hint">pending</td>' in SRC
    assert "weekCell(st ? st.week_rel : null, m)" in SRC
    assert "fmt(st ? st.cum_rel : null)" in SRC
    # the verdict is driven by this week's official dict and the season
    # catalog the host supplies, never by a separate payload field
    assert "officialAvailability(pl, OFFS)" in SRC
    assert "weekCellState(v, OFFS.indexOf(m) >= 0" in SRC
    assert "!!seasonOffs[m]" in SRC


def test_no_forecast_note_is_wired_into_the_frame_draw():
    # drawFC computes availability across ALL models (toggled or not) and
    # sets the caption from the shared helper on every frame, so an empty
    # frame can never again render as silent bare axes
    assert "el.msg.textContent = noForecastNote(loc, avail, drawn)" in SRC
    assert "noForecastNote: noForecastNote" in SRC


def test_view_state_clear_sites():
    # stored from plotly relayout events, cleared on double click,
    # location change, and the Lock axes toggle
    assert "plotly_relayout" in SRC and "plotly_doubleclick" in SRC
    assert SRC.count("P.user = {x: null, y: null}") >= 3
    # and the stored view overrides the lock (or auto) ranges on redraw
    assert "if(P.user.x){ xa.range = P.user.x.slice()" in SRC
    assert "if(P.user.y){ ya.range = P.user.y.slice()" in SRC
