"""Design batch three: the retro index states a completed season's verdict;
the cumulative relWIS chart carries its own scale; the per-state table
colors only exceptions; fan bands derive from the displayed member's color;
one shared model-name map; the report download is a primary button; the
Forecast tab survives a restart; no native confirm() on /data; the
Hospitalized compartment is not Inhibition Red.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui import server as srv                    # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons  # noqa: E402
from app.ui import shared as ui_shared              # noqa: E402
from app.ui import state as ui_state                # noqa: E402
from app.ui import templating as ui_templating      # noqa: E402

client = TestClient(srv.app)

UI = Path(__file__).resolve().parents[1] / "ui"
NAU = (UI / "static" / "nau.css").read_text()
PLAYER = (UI / "static" / "player.js").read_text(encoding="utf-8")
#: every console module's source, by path under app/ui
UI_PY = {p.relative_to(UI).as_posix(): p.read_text(encoding="utf-8")
         for p in sorted(UI.rglob("*.py"))}
RETRO_T = (UI / "templates" / "retro.html").read_text()
SEASON_T = (UI / "templates" / "retro_season.html").read_text()
FORECAST_T = (UI / "templates" / "forecast.html").read_text()
MODEL_T = (UI / "templates" / "model.html").read_text()
DATA_T = (UI / "templates" / "data.html").read_text()
DIAGRAMS_T = (UI / "templates" / "diagrams.html").read_text()

SEASON = "2098-99"


def _index_card(**kw):
    d = {"name": SEASON, "total": 30, "done": 30, "seal": False,
         "running": False, "paused": False, "active": False,
         "status": "done", "elapsed_s": None, "mean_s": None,
         "weeks_measured": 0, "eta_s": None, "scored": True, "rel": 0.877}
    d.update(kw)
    return d


def _index(**kw):
    return srv.templates.env.get_template("retro.html").render(
        active="Retrospective", state_names=["Ohio"], engine_ok=True,
        seasons=[_index_card(**kw)])


def _season_ctx(**kw):
    ctx = dict(active="Retrospective", season=SEASON,
               heads={"ensemble": 0.9},
               curve=[("2098-11-07", 0.95), ("2098-11-14", 0.9)],
               states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1,
                        "ensemble": None}],
               weeks=["2098-11-07", "2098-11-14"], week="2098-11-14",
               map_html="<div id='usmap-wrap'></div>",
               official_catalog=[], n_weeks=2, score_error="")
    ctx.update(kw)
    return ctx


def _season(**kw):
    return srv.templates.env.get_template("retro_season.html").render(
        **_season_ctx(**kw))


# ------------------------------------- finding 17: index states the verdict

def test_completed_season_prints_relwis_instead_of_the_bar():
    html = _index()
    # the archived-row encoding, beside the Results button
    assert 'relWIS <span class="ok">0.877</span>' in html
    assert "<progress" not in html


def test_completed_season_losing_to_baseline_wears_bad():
    html = _index(rel=1.023)
    assert 'relWIS <span class="bad">1.023</span>' in html


def test_active_and_unfinished_seasons_keep_their_bars():
    live = _index(done=3, status="running", running=True, active=True,
                  rel=None)
    assert 'class="runbar"' in live
    assert "relWIS" not in live
    part = _index(done=3, status="stopped", rel=0.9)
    assert "<progress" in part                # incomplete: bar, not verdict
    assert "relWIS" not in part
    unscored = _index(rel=None)               # complete but never scored
    assert "<progress" in unscored


def test_index_route_passes_the_head_score(tmp_path, monkeypatch):
    from app.core import retro
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: ["w"] * 2)
    monkeypatch.setattr(retro, "run_summary", lambda root: {
        "weeks": 2, "elapsed_s": None, "started_utc": None,
        "finished_utc": None, "status": "done", "scored": True,
        "headline_rel": 0.877})
    monkeypatch.setattr(ui_retro_seasons, "_season_root",
                        lambda s, archive="": (tmp_path / s, False))
    monkeypatch.setattr(ui_retro_seasons, "_weeks_done", lambda root: 2)
    monkeypatch.setattr(ui_retro_seasons, "_archive_entries", lambda s: [])
    monkeypatch.setattr(ui_retro_seasons, "_retro_progress", lambda s: {
        "season": s, "status": "done", "done": 2, "total": 2,
        "settings": [], "elapsed_s": None, "weeks_measured": 0,
        "mean_s": None, "eta_s": None, "slowest_week": None,
        "slowest_s": None, "started_utc": None, "finished_utc": None,
        "active": False})
    r = client.get("/retro")
    assert r.status_code == 200
    assert 'relWIS <span class="ok">0.877</span>' in r.text
    assert "<progress" not in r.text


# --------------------------------- finding 18: the chart carries its scale

def test_cumulative_chart_prints_terminal_value_dates_and_both_gridlines():
    html = _season()
    assert ">0.900</text>" in html            # the final cumulative value
    assert ">1.0</text>" in html and ">0.5</text>" in html
    assert ">2098-11-07</text>" in html       # first week under the corner
    assert ">2098-11-14</text>" in html       # last week under the corner
    # labels ride the rem classes, never fixed viewBox-unit sizes
    assert 'font-size="' not in SEASON_T


def test_cumulative_chart_y_range_hugs_the_data():
    # scores near 0.9 land at DIFFERENT heights: the range hugs the data
    html = _season(curve=[("2098-11-07", 0.95), ("2098-11-14", 0.90)])
    ys = re.findall(r'<circle data-week="[^"]*" cx="[\d.]+" cy="([\d.]+)"', html)
    assert len(ys) == 2
    assert abs(float(ys[0]) - float(ys[1])) > 5


def test_cumulative_chart_absent_curve_says_so():
    html = _season(curve=[])
    assert "Arrives with the first scored week." in html


# ------------------------- finding 20: exceptions only, numerals aligned

def test_per_state_table_colors_only_scores_at_or_above_one():
    html = _season(states=[{"name": "Ohio", "pf": 0.9, "analogue": 1.1},
                           {"name": "Utah", "pf": 0.8, "analogue": None}])
    body = html.split("Per-state scores")[1].split("</table>")[0]
    assert re.search(r'<td class="num bad">\s*1\.100</td>', body)
    assert re.search(r'<td class="num">\s*0\.900</td>', body)   # quiet win
    assert 'class="num ok"' not in body
    assert re.search(r'<td class="num">\s*n/a</td>', body)
    # the headers are aria-pressed sort buttons with the shared model names;
    # the retired blend has no column
    assert 'data-key="ensemble"' not in body
    for key, label in (("pf", "Oracle SIHRS"), ("analogue", "Groundhog")):
        assert re.search(r'<th class="num"><button type="button" '
                         r'class="thsort" data-key="' + key + r'"\s+'
                         r'aria-pressed="false">' + label, body), key


def test_num_class_right_aligns_everywhere():
    assert "td.num,th.num{text-align:right}" in NAU


# --------------------- finding 16: bands wear the displayed member's color

def test_fan_bands_derive_from_the_displayed_member():
    for src, name in ((FORECAST_T, "forecast"), (MODEL_T, "model")):
        assert "rgba(255,199,44" not in src, name   # the hardcoded analogue
        assert "fillcolor:rgba(mc,.2)" in src, name
        assert "line:{color:mc,width:2.5}" in src, name
        assert "function memberColor(m)" in src, name
    assert "memberColor(FMODEL)" in FORECAST_T      # the selected model
    assert "memberColor(MNAME)" in MODEL_T          # this page's model


def test_member_colors_match_the_player_palette():
    # ONE member-color source (player.js marked JSON): templates use the
    # server-injected copy, the season page reads FluBNFPlayer; ensemble
    # alone resolves through the accent token
    for src in (FORECAST_T, MODEL_T):
        assert "css('--gold')||MCOLORS.ensemble" in src
        assert "const MCOLORS = {{ member_colors_json | safe }}" in src
        assert "MCOLORS[m]||css('--mut')" in src
        assert "#6E8FD0" not in src and "#2BB5A0" not in src
        assert "#FFC72C" not in src                 # no private literals
    assert "FluBNFPlayer.MODEL_COLORS" in SEASON_T
    assert "#6E8FD0" not in SEASON_T and "#2BB5A0" not in SEASON_T
    # the injected copy IS the player's map
    from app.core.report_v2 import model_colors
    assert ui_templating._member_colors() == model_colors()
    r = client.get("/forecast")
    assert json.dumps(model_colors()["pf"])[1:-1] in r.text


def test_player_carries_the_color_map_and_python_reads_the_same_one():
    m = re.search(r"/\*MODEL_COLORS_JSON\*/\s*(\{.*?\})"
                  r"\s*/\*END_MODEL_COLORS_JSON\*/", PLAYER, re.S)
    assert m, "player.js must carry the marked JSON member-color map"
    colors = json.loads(m.group(1))
    from app.core import report_season
    from app.core.report_v2 import MEMBER_COLORS, model_colors
    assert model_colors() == colors                 # one source, no drift
    assert MEMBER_COLORS == colors
    assert report_season.MODEL_COLORS == colors
    # the player's default palette rides the same object
    assert "models: MODEL_COLORS" in PLAYER
    # and the weekly report's fan bands derive from the pf member's color
    from app.core.report_v2 import QBANDS
    r, g, b = (int(colors["pf"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    assert all(f"rgba({r},{g},{b}," in band[2] for band in QBANDS)


# --------------------------------- finding 24: one shared model-name map

def _player_map():
    m = re.search(r"/\*MODEL_NAMES_JSON\*/\s*(\{.*?\})"
                  r"\s*/\*END_MODEL_NAMES_JSON\*/", PLAYER, re.S)
    assert m, "player.js must carry the marked JSON model-name map"
    return json.loads(m.group(1))


def test_player_carries_the_map_and_python_reads_the_same_one():
    names = _player_map()
    for mid in ("pf", "analogue", "ensemble", "pf2s",
                "FluSight-baseline", "FluSight-ensemble"):
        assert mid in names, mid
    from app.core import report_season
    assert report_season.MODEL_NAMES == names       # one source, no drift
    assert ui_templating._model_names() == names
    # the player's own display-name lookup reads the shared map
    assert "return MODEL_NAMES[m] || m" in PLAYER


def test_one_name_for_the_ensemble_on_every_human_facing_surface():
    """The blend is "FluBNF Ensemble (retired)" on every human-facing surface
    (stored runs still carry its rows); display names never change the hub
    ids.
    """
    from app.core import report_v2, site_page
    assert _player_map()["ensemble"] == "FluBNF Ensemble (retired)"
    # map labels append "categorical forecast"; typed in report_v2, where
    # drift would happen
    names = _player_map()
    assert report_v2.MODEL_LABEL == {m: names[m] + " categorical forecast"
                                     for m in report_v2.MODEL_LABEL}
    # no surface carries the old name
    site_src = Path(site_page.__file__).read_text()
    assert '"ensemble": "FluBNF Ensemble (retired)"' in site_src
    for src in (PLAYER, site_src, SEASON_T, RETRO_T, MODEL_T, FORECAST_T):
        assert "NAU ensemble" not in src
    # submission identities are display-independent
    from app.core import submit
    assert submit.hub_model_id("pf") == "NAU_PyBNF-OracleSIHRS"
    assert submit.hub_model_id("analogue") == "NAU_PyBNF-GroundHogCGR"
    assert submit.RETIRED_ABBR == ()


def test_template_global_resolves_names_and_passes_unknowns_through():
    name = srv.templates.env.globals["model_name"]
    assert name("pf") == "Oracle SIHRS"
    assert name("ensemble") == "FluBNF Ensemble (retired)"
    assert name("analogue") == "Groundhog"
    assert name("mystery") == "mystery"


def test_season_head_cards_wear_the_shared_names():
    html = _season(heads={"ensemble": 0.9, "pf": 1.02})
    assert "<h2>FluBNF Ensemble (retired)</h2>" in html
    assert "<h2>Oracle SIHRS</h2>" in html
    assert "<h2>pf</h2>" not in html and "<h2>ensemble</h2>" not in html


def test_fan_selector_buttons_use_the_shared_names():
    assert "const MNAMES" in FORECAST_T
    assert "(MNAMES[m]||m)" in FORECAST_T           # button labels
    r = client.get("/forecast")
    assert r.status_code == 200
    assert '"pf": "Oracle SIHRS"' in r.text             # the map ships to the page


def test_model_switcher_reads_the_shared_map():
    t = client.get("/models").text
    for label in ("Oracle SIHRS", "Groundhog", "Two-strain SIHRS"):
        assert label in t, label
    # no switcher tab for the retired blend (the shared map still ships it)
    assert 'data-model="ensemble"' not in t
    assert "model_name(mn)" in MODEL_T              # not a fourth hardcoding


# ------------------- finding 15: the Forecast tab survives an app restart

def test_stored_forecasts_render_without_a_session_gate(monkeypatch):
    res = {"forecast_date": "2098-11-14",
           "models": {"pf": {"Ohio": {"1": {"0.1": 1.0, "0.5": 2.0,
                                                  "0.9": 3.0}}}},
           "observed": {}}
    monkeypatch.setattr(ui_shared, "_latest_results", lambda: ("r1", res))
    monkeypatch.setitem(ui_state._status, "running", None)
    ui_state._status.pop("session_ran", None)            # a fresh process has none
    r = client.get("/forecast")
    assert r.status_code == 200
    assert '"pf": {"Ohio"' in r.text          # the stored fans ship
    assert "latest stored run" in r.text            # and the title says so
    # the gate is gone from the codebase, not merely bypassed
    assert [f for f, src in UI_PY.items() if "session_ran" in src] == []


def test_latest_run_card_links_report_and_files():
    assert 'href="/runs/{{ r.run_id }}/report"' in FORECAST_T
    assert 'href="/output"' in FORECAST_T


# ------------------------ finding 25: the download wears the primary tier

def test_download_season_report_is_a_gold_button():
    html = _season()
    assert re.search(r'<a href="/retro/2098-99/report" download>'
                     r'<button class="gold"', html)
    # Reveal stays quiet beside it
    assert 'class="quiet" id="rev-report"' in html


# ------------------------------- finding 26: no native confirm on /data

def test_data_page_has_no_native_confirm():
    assert "return confirm(" not in DATA_T
    assert "onsubmit" not in DATA_T
    t = client.get("/data").text
    assert "Pull the FluSight hub now?" not in t
    assert 'data-guard="data-pull"' in t            # the guard remains


# ------------------------------- finding 27: red stays semantic

def test_hospitalized_compartment_is_not_inhibition_red():
    assert "var(--bad)" not in DIAGRAMS_T
    assert 'fill="var(--slate)"' in DIAGRAMS_T
    t = client.get("/models").text
    assert 'fill="var(--bad)"' not in t
