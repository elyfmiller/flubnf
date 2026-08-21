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
SRC = PLAYER.read_text()
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


@needs_jsc
def test_add_days_utc(tmp_path):
    assert _js(tmp_path, "I.addDays('2098-12-02', 28)") == "2098-12-30"


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
    # every model toggle carries an availability note span; an official
    # absent from the current payload disables its checkbox and fills the
    # note with the fetch hint, refreshed on every payload
    assert "data-avail" in SRC
    assert "(fetch via Update data on the Data tab)" in SRC
    assert "box.disabled = !av[m]" in SRC
    assert "officialAvailability(pl, OFFS)" in SRC
    assert "updateAvailability(pl)" in SRC


def test_view_state_clear_sites():
    # stored from plotly relayout events, cleared on double click,
    # location change, and the Lock axes toggle
    assert "plotly_relayout" in SRC and "plotly_doubleclick" in SRC
    assert SRC.count("P.user = {x: null, y: null}") >= 3
    # and the stored view overrides the lock (or auto) ranges on redraw
    assert "if(P.user.x){ xa.range = P.user.x.slice()" in SRC
    assert "if(P.user.y){ ya.range = P.user.y.slice()" in SRC
