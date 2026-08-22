"""Accessibility basics across the console shell.

One coherent pass: the document language and skip link (Level A), the
modal focus contract (focus in on open, a Tab loop inside, focus returned
on close), honest toggle states on every view switcher, playback that
announces itself to assistive tech, motion accommodation for the quip
rotation and animated fills, the light-theme accent-ink repointing for the
structural cyan, the dark-theme field boundary token, the destructive
button tier, and the prose measure cap.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
QUIPS = (UI / "static" / "quips.js").read_text()
PLAYER = (UI / "static" / "player.js").read_text()
SEASON_T = (UI / "templates" / "retro_season.html").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()


# ------------------------------------------------- document shell (Level A)

def test_document_language_and_skip_link():
    html = client.get("/data").text
    assert '<html lang="en">' in html
    assert 'class="skip" href="#main"' in html
    # the shell's main_class block (the centered reading column opt-in)
    # renders an empty class attribute on operational pages
    assert '<main id="main" class="' in html
    # the skip link precedes the header, so it is the first tab stop
    assert html.index('class="skip"') < html.index('<header class="nav">')
    assert "a.skip:focus{left:0}" in NAU


# ------------------------------------------------------ modal focus contract

def test_modals_move_hold_and_return_focus():
    html = client.get("/data").text
    # a Tab loop is installed on both dialog shells
    assert "trapTab(back)" in html
    assert "trapTab(so.back)" in html
    # opening focuses the Cancel button of the row on show
    assert "cancel.focus()" in html
    assert "document.getElementById('so-cancel').focus()" in html
    assert "document.getElementById('so-cancel2').focus()" in html
    # closing returns focus to the element that opened the dialog
    assert "function refocus(el)" in html
    assert html.count("refocus(t)") >= 2
    # Escape handling is unchanged
    assert "e.key==='Escape'" in html


# ---------------------------------------------------- honest toggle states

def test_retro_view_switcher_is_plain_pressed_buttons():
    # the tablist promise (aria-controls, tabpanels, arrow keys) is not
    # kept, so it is not made: plain buttons state aria-pressed instead
    assert 'role="tablist"' not in SEASON_T
    assert 'role="tab"' not in SEASON_T
    assert "aria-selected" not in SEASON_T
    assert 'role="group" aria-label="Playback view"' in SEASON_T
    assert 'id="tab-map" aria-pressed="true"' in SEASON_T
    assert 'id="tab-fc" aria-pressed="false"' in SEASON_T
    assert "setAttribute('aria-pressed'" in SEASON_T


def test_forecast_data_view_toggles_mark_the_selected_mode():
    # drawData marks the active mode with gold exactly as setView does,
    # and states it for assistive tech
    assert "classList.toggle('gold', mode===m)" in FORECAST_T
    assert "setAttribute('aria-pressed', String(mode===m))" in FORECAST_T
    for bid in ("mode-raw", "mode-season", "mode-pts"):
        assert f'id="{bid}" aria-pressed="false"' in FORECAST_T, bid
    # the points toggle reports its own pressed state
    assert "setAttribute('aria-pressed', String(SHOWPTS))" in FORECAST_T


# ------------------------------------------------- playback announcements

def test_player_labels_play_state_and_announces_weeks():
    from app.core.report_season import _PAGE
    # the shared player owns the play button's accessible name, per state
    assert "labelPlay" in PLAYER
    assert "on ? 'Pause' : 'Play'" in PLAYER
    # no host pins the misreporting static label
    assert 'aria-label="Play or pause"' not in SEASON_T
    assert 'aria-label="Play or pause"' not in _PAGE
    # week and status readouts are polite live regions in both hosts
    assert 'id="pb-week" aria-live="polite"' in SEASON_T
    assert 'id="pb-status" aria-live="polite"' in SEASON_T
    assert 'id="pb-week" aria-live="polite"' in _PAGE
    assert 'id="pb-status" aria-live="polite"' in _PAGE


# ------------------------------------------------------ motion accommodation

def test_quips_hold_still_under_reduced_motion_and_on_click():
    assert "prefers-reduced-motion" in QUIPS
    # click-to-pause on the quip element itself
    assert 'addEventListener("click"' in QUIPS
    # a static line still paints when rotation never starts
    assert "el.textContent = q[i++ % q.length];" in QUIPS
    # and the css block quiets animated fills
    assert "@media (prefers-reduced-motion: reduce)" in NAU


# ------------------------------------------------- light-theme structural ink

def test_structural_cyan_reads_through_accent_ink():
    # the token pair: readable in light, pure cyan in dark
    assert "--accent-ink:#0173A9" in NAU
    assert "--accent-ink:#34C0F0" in NAU
    for rule in ("header.nav .brand em{color:var(--accent-ink)",
                 "border-bottom-color:var(--accent-ink)",
                 "progress::-webkit-progress-value{background:var(--accent-ink)",
                 "progress::-moz-progress-bar{background:var(--accent-ink)"):
        assert rule in NAU, rule
    assert "background:var(--accent-ink)}" in NAU     # the runbar fill


# ----------------------------------------------------- dark field boundaries

def test_form_fields_carry_the_dark_boundary_token():
    assert "--field-line:#5B639E" in NAU              # dark: 3.43:1 vs the well
    assert "border:1px solid var(--field-line)" in NAU


# ------------------------------------------------------ destructive tier

def test_destructive_confirms_wear_the_danger_tier():
    html = client.get("/data").text
    assert 'class="danger" id="guard-stop"' in html
    assert 'class="danger" id="so-ok"' in html
    # archive-and-start-fresh is safe and keeps the primary accent
    assert 'class="gold" id="so-archive"' in html
    assert "button.danger" in NAU
    assert "background:var(--bad);border-color:var(--bad)" in NAU


# ------------------------------------------------------- prose measure cap

def test_prose_measure_cap_spares_hints_and_tables():
    assert "max-width:72ch" in NAU
    # hints and the sub intro lines both escape the measure (heading-width
    # uniformity, user 2026-08-21: intro text spans the card width)
    assert ".card p.hint,.card p.sub{max-width:none}" in NAU
