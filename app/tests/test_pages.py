"""Page renders: home workflow diagram and performance table, model-tab
diagrams and collapsible intros, methods anchors and backlinks, ensemble
member overlay wiring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient           # noqa: E402

from app.ui.server import app as srv                # noqa: E402

client = TestClient(srv)


def test_home_renders_workflow_performance_and_component_cards():
    r = client.get("/")
    assert r.status_code == 200
    assert "mechanistically" in r.text              # tagline kept
    # the interactive mechanism panel is gone from home; it stays on the
    # model pages and under Methods
    assert "SIHRS compartment diagram" not in r.text
    assert 'id="diag-loc"' not in r.text            # no region select
    assert 'id="vals-1"' not in r.text              # no values panel
    assert "const DIAG" not in r.text               # no diagram feed script
    # weekly workflow pipeline diagram
    assert "Weekly forecasting workflow" in r.text
    assert "10,000 candidate epidemics" in r.text
    assert "Equal-weight blend" in r.text
    # measured performance: the three-season seal table, now carrying the
    # field percentile per season and a mean on the pooled row
    assert 'class="perf"' in r.text
    for cell in ("0.848", "0.651", "0.691", "0.704",
                 "14 of 34 teams", "4 of 40 teams", "19 of 47 teams",
                 "Percentile", "61st", "92nd", "mean 71st"):
        assert cell in r.text, cell
    # the two-strain member is settled, not pending
    assert "full-grid validation is in progress" not in r.text
    # component cards lead with a visual and keep links and versions
    assert 'alt="PyBNF brand mark"' in r.text
    assert "Simulation-trace glyph" in r.text
    assert "Contact-map glyph" in r.text
    assert "github.com/lanl/PyBNF" in r.text
    assert "github.com/lanl/bngsim" in r.text
    assert "bionetgen.org" in r.text
    assert 'target="_blank"' in r.text
    assert "/methods#sihrs" in r.text               # anchor into methods
    # start-here numbered flow: vertical stepper, equal-weight copy honest
    assert 'class="steps"' in r.text
    assert 'class="stepnum"' in r.text
    assert "never fitted" in r.text
    assert "frozen" not in r.text


def test_two_strain_is_off_the_navbar_but_still_routed():
    """It failed the full-grid ensemble gate: the nav affordance goes, the
    route stays so existing links and the research path survive."""
    home = client.get("/")
    assert 'href="/model/pf2s"' not in home.text
    assert "Two-strain SIHRS</a>" not in home.text
    assert client.get("/model/pf2s").status_code == 200


# --------------------------------------------- navigation (operational loop)

import re                                           # noqa: E402


def _nav_tabs(html):
    return re.findall(r'<a class="tab[^"]*" href="([^"]+)">([^<]+)</a>',
                      html)


def _pressed_model(html):
    m = re.search(r'aria-pressed="true"\s+data-model="(\w+)"', html)
    return m.group(1) if m else None


def test_nav_is_the_operational_loop():
    """The tab set walks the workflow the home page teaches, and the three
    model reference pages collapse behind the one Models tab."""
    tabs = _nav_tabs(client.get("/").text)
    assert [h for h, _ in tabs] == ["/", "/data", "/forecast", "/output",
                                    "/retro", "/runs", "/models",
                                    "/methods"]
    assert [n for _, n in tabs] == ["Home", "Data", "Forecast", "Output",
                                    "Retrospective", "Runs", "Models",
                                    "Methods"]


def test_models_route_defaults_to_pf_and_owns_the_active_tab():
    r = client.get("/models")
    assert r.status_code == 200
    assert "PF-SIHRS" in r.text
    assert _pressed_model(r.text) == "pf"
    assert re.search(r'<a class="tab active" href="/models">Models</a>',
                     r.text)


def test_old_model_routes_stay_live_with_the_right_switcher_state():
    """Exported reports and bookmarks link /model/<name>; each still serves
    the page, presses its own switcher button, and lights the Models tab."""
    for name in ("pf", "analogue", "ensemble", "pf2s"):
        t = client.get(f"/model/{name}").text
        assert _pressed_model(t) == name, name
        assert t.count('aria-pressed="true"') == 1, name
        assert re.search(r'<a class="tab active" href="/models">Models</a>',
                         t), name


def test_switcher_lists_two_strain_as_the_research_option():
    t = client.get("/models").text
    assert t.count("data-model=") == 4
    assert "Two-strain SIHRS" in t
    assert "(research)" in t


def test_model_pages_render_mechanism_and_collapsed_intro():
    markers = {
        "pf": "SIHRS compartment diagram",
        "pf2s": "Influenza A circuit",
        "analogue": "forecast date",                # analogue mechanism svg
        "ensemble": "quantile average",             # blend node
    }
    for name, marker in markers.items():
        r = client.get(f"/model/{name}")
        assert r.status_code == 200, name
        assert marker in r.text, name
        # intro collapsed by default: a details block without `open`
        assert '<details class="card intro">' in r.text, name
        assert 'href="/methods#' in r.text, name


def test_ensemble_page_carries_member_overlay():
    r = client.get("/model/ensemble")
    assert r.status_code == 200
    assert "const OVERLAY" in r.text
    assert "legendonly" in r.text


def test_forecast_page_renders_with_ensemble_overlay_js():
    r = client.get("/forecast")
    assert r.status_code == 200
    assert "legendonly" in r.text


def test_methods_anchors_and_backlinks():
    r = client.get("/methods")
    assert r.status_code == 200
    for anchor in ('id="sihrs"', 'id="fitting"', 'id="two-strain"',
                   'id="analogue"', 'id="ensemble"'):
        assert anchor in r.text, anchor
    for back in ('href="/model/pf"', 'href="/model/pf2s"',
                 'href="/model/analogue"', 'href="/model/ensemble"'):
        assert back in r.text, back
    # the respread diagram: no label sits on the return arc anymore
    assert "M762,182 C762,330 87,330 87,182" in r.text


def test_map_legend_carries_all_categories_and_the_no_data_swatch():
    from app.core.usmap import CAT_COLOR, map_legend
    lg = map_legend()
    for color in CAT_COLOR.values():
        assert color in lg, color
    for label in ("large decrease", "decrease", "stable", "increase",
                  "large increase", "no data"):
        assert label in lg, label
    assert "var(--map-nodata" in lg               # theme-following gap tone
    assert lg.count('class="sw"') == 6            # five categories + no data
    assert 'class="hint maplegend"' in lg


def test_home_outlook_card_has_heading_and_legend():
    r = client.get("/")
    assert r.status_code == 200
    # the card names its payload like every other card in the app
    assert "US outlook" in r.text
    # and the legend rides with the map, so the encoding is readable
    # without hovering
    assert 'class="hint maplegend"' in r.text
    assert "no data" in r.text


def test_home_outlook_caption_states_coverage_when_a_run_exists():
    from app.ui.server import templates
    html = templates.env.get_template("home.html").render(
        active="Home", map_svg="<svg></svg>", outlook_date="2026-01-24",
        outlook_n=1, missing=[],
        versions={"pybnf": "x", "bngsim": "x", "bionetgen": "x",
                  "fastapi": "x", "plotly": "x"})
    assert "US outlook · 2026-01-24" in html      # dated in the heading
    assert "cover 1 of 52" in html                # one green state is not a
    assert "the rest show as no data" in html     # national outlook
    # without a run, the card stays honest about being empty
    empty = templates.env.get_template("home.html").render(
        active="Home", map_svg="", outlook_date="", outlook_n=0, missing=[],
        versions={"pybnf": "x", "bngsim": "x", "bionetgen": "x",
                  "fastapi": "x", "plotly": "x"})
    assert "Fills in when you run a forecast." in empty
    assert "of 52" not in empty


# ----------------- defining equations, tied to the models they define

def test_model_pages_carry_their_defining_equations():
    wanted = {
        "pf": ("NegBin(", "filter bends each week", "Fitted per state"),
        "pf2s": ("Binomial(", "one harmonic form shared by both circuits",
                 "second likelihood channel"),
        "analogue": ("calendar-matched historical growth",),
        "ensemble": ("equal-weight mean of the",),
    }
    for name, needles in wanted.items():
        t = client.get(f"/model/{name}").text
        assert 'class="eqpanel"' in t, name
        for needle in needles:
            assert needle in t, (name, needle)


def test_methods_carries_the_pf_and_two_strain_equations():
    t = client.get("/methods").text
    assert t.count('class="eqpanel"') == 2       # SIHRS card + two-strain card
    assert "NegBin(" in t
    assert "Binomial(" in t


def test_home_workflow_carries_the_forcing_and_blend_equations():
    t = client.get("/").text
    assert 'class="eqpanel"' in t
    assert "the curve the filter bends each week" in t
    assert "mean<sub>m</sub>" in t               # the ensemble quantile mean


# --------------------------- read-only BNGL source on BNGL-backed pages

def test_bngl_source_is_shown_escaped_on_bngl_backed_pages():
    pf = client.get("/models").text
    assert "View model source (BNGL)" in pf
    assert "SIHRS_pop_min.bngl" in pf
    # collapsed by default: a details block without `open`
    assert '<details class="card bngl">' in pf
    # contents escaped into text, never interpreted as markup
    assert "S() + I() -&gt; I() + I()" in pf
    # substitution tokens shown as-is, with the hint that explains them
    assert "{{POP}}" in pf
    assert "filled in per state and week" in pf
    p2 = client.get("/model/pf2s").text
    assert "View model source (BNGL)" in p2
    assert "SIHRS_pop_2strain_min.bngl" in p2
    assert "{{POP}}" in p2


def test_models_without_bngl_get_no_source_block():
    for name in ("analogue", "ensemble"):
        t = client.get(f"/model/{name}").text
        assert "View model source" not in t, name
        assert 'class="card bngl"' not in t, name


# ------------------------------------------- diagram macro conventions

def test_diagram_svgs_use_aria_label_not_hover_title():
    """<svg><title> doubles as a hover tooltip that pops over the artwork;
    the accessible name rides aria-label instead."""
    t = (Path(__file__).resolve().parents[1] / "ui" / "templates"
         / "diagrams.html").read_text(encoding="utf-8")
    assert "<title" not in t
    for label in ("SIHRS compartment diagram",
                  "Two-strain SIHRS compartment diagram",
                  "Calendar analogue mechanism",
                  "Ensemble blending diagram"):
        assert f'aria-label="{label}"' in t, label


def test_analogue_legend_wraps_inside_the_viewbox():
    """The single-line legend entries clipped at the right viewBox edge once
    the A+ text step multiplied the rem-sized labels; long entries now wrap
    onto continuation lines."""
    t = client.get("/model/analogue").text
    assert "same calendar weeks,</text>" in t
    assert "same calendar weeks, prior seasons" not in t


def test_two_strain_caption_is_two_drawn_lines():
    t = client.get("/model/pf2s").text
    assert "Observed admissions sum the A and B fluxes;</text>" in t


def test_diagram_data_shapes():
    from app.ui.server import _diagram_data
    assert _diagram_data(None) == {"date": "", "has_pf2s": False,
                                   "locations": {}, "order": []}
    res = {"forecast_date": "2026-08-15",
           "params": {"pf": {"Ohio": {"Reff": 1.07, "phi1": 27.2}},
                      "pf2s": {"Ohio": {"ReffA": 1.0, "ReffB": 1.04}}},
           "observed": {"Ohio": [["2026-08-08", 12.0]],
                        "US": [["2026-08-08", 300.0]]},
           "models": {"ensemble": {"Ohio": {"1": {"0.5": 14.0}}}}}
    d = _diagram_data(res)
    assert d["has_pf2s"] is True
    assert d["order"][0] == "US"                    # national listed first
    assert d["locations"]["Ohio"]["pf"]["Reff"] == 1.07
    assert d["locations"]["Ohio"]["med1"] == 14.0
    assert d["locations"]["Ohio"]["obs"] == [["2026-08-08", 12.0]][-1]
    assert "pf" not in d["locations"]["US"]         # graceful omission
