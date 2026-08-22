"""The run-settings block: one shared renderer, a compact two-column table.

User report 2026-08-21: the 'Run settings: forecast date ... particles ...'
prose lines read as small print with a page-wide dead band. The one shared
renderer (app.core.runs.settings_html) now emits a tight two-column
label/value grid (dl.kv, the definition-grid style: natural width, values
in tabular figures) at the standard body size, and every surface renders
through it -- the forecast running card, the run page, the retro index's
season cards, the retro season page, and both report exports -- so all
surfaces render identically by construction.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.runs import settings_html              # noqa: E402

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
RUN_T = (UI / "templates" / "run.html").read_text()
RETRO_T = (UI / "templates" / "retro.html").read_text()
SEASON_T = (UI / "templates" / "retro_season.html").read_text()

PAIRS = [("forecast date", "2026-01-24"), ("engine", "all"),
         ("locations", "Ohio, US"), ("particles", "10,000")]


# ------------------------------------------------------------ the renderer

def test_renderer_emits_the_two_column_grid():
    html = settings_html(PAIRS)
    assert html.startswith('<div class="hint runsettings">')
    assert "<strong>Run settings</strong>" in html
    assert '<dl class="kv">' in html
    # label/value pairs in order, dt then dd
    assert re.search(r"<dt>forecast date</dt><dd>2026-01-24</dd>", html)
    assert re.search(r"<dt>particles</dt><dd>10,000</dd>", html)
    # the old one-line prose rendering is gone
    assert " · " not in html
    assert "Run settings:" not in html


def test_renderer_escapes_values_and_keeps_the_contracts():
    html = settings_html([("locations", '<b>&"x')], title="Settings",
                         cls="sub", el_id="rs")
    assert "&lt;b&gt;&amp;&quot;x" in html
    assert "<b>&" not in html
    # any caller-supplied class keeps the runsettings hook the grid styles
    # hang from, and the el_id survives
    assert 'class="sub runsettings"' in html
    assert 'id="rs"' in html
    # empty input still renders nothing at all
    assert settings_html([]) == ""
    assert settings_html([("a", ""), ("b", None)]) == ""


def test_report_freshness_marker_survives():
    """report_season keys its cache freshness on the literal SETTINGS_MARK
    ('Run settings') appearing in the rendered block."""
    from app.core.report_season import SETTINGS_MARK
    assert SETTINGS_MARK in settings_html(PAIRS, title=SETTINGS_MARK)


# ------------------------------------------------------------- the styles

def test_stylesheet_carries_the_grid_at_body_size():
    joined = " ".join(NAU.split())
    assert ".runsettings .kv{display:grid;" in joined
    assert "grid-template-columns:max-content max-content;" in joined
    # natural width, never page-wide
    assert "width:max-content" in joined.split(".runsettings .kv{")[1] \
        .split("}")[0]
    # standard body size, not the small print the hint class would give
    assert "font-size:var(--fs-body)" in joined.split(".runsettings .kv{")[1] \
        .split("}")[0]
    assert ".runsettings .kv dt{color:var(--mut)}" in joined
    # both self-contained report exports restate the grid
    for mod in ("report_v2", "report_season"):
        src = (Path(__file__).resolve().parents[1] / "core"
               / f"{mod}.py").read_text()
        assert ".runsettings .kv" in src, mod


# ---------------------------------------------------------- the surfaces

def test_every_surface_renders_through_the_shared_renderer():
    # forecast running card AND latest-run card, run page (settings +
    # versions), retro index season cards, retro season page (live replay
    # + finished record)
    assert "settings_html(status.settings)" in FORECAST_T
    assert "settings_html(r.settings)" in FORECAST_T
    assert 'settings_html(settings, title="Settings")' in RUN_T
    assert 'settings_html(versions, title="Produced by")' in RUN_T
    assert "settings_html(s.settings)" in RETRO_T
    assert SEASON_T.count("settings_html(prog.settings)") == 2


def test_forecast_poll_fallback_builds_the_same_markup():
    """The running card can render before the spec exists; the poll fills
    it in client-side with exactly the shared renderer's markup, values
    escaped (they include location names)."""
    seg = FORECAST_T.split("runsettings'", 1)[0]
    assert '<div class="hint runsettings"><strong>Run settings</strong>' \
        in FORECAST_T
    assert "'<dt>'+esc(p[0])+'</dt><dd>'+esc(p[1])+'</dd>'" in FORECAST_T
    assert "replace(/</g,'&lt;')" in FORECAST_T
    # the old prose fallback is gone
    assert "join(' · ')" not in FORECAST_T
    assert seg is not None
