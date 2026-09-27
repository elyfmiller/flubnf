"""The Models tab reads as headings, values and controls.

Every sentence the model pages used to print is still on the page, moved
into a "?" or an "i" beside the thing it explains (docs/UI-KIT.md); the
equation panels wear names with their notes in tips on the console only,
and stay plain where the public site and Methods render them.
"""
import re
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core import oracle_text as ot                # noqa: E402
from app.ui import shared as ui_shared                # noqa: E402
from app.ui import state as ui_state                  # noqa: E402
from app.ui.server import app as srv                  # noqa: E402

client = TestClient(srv)
TEMPLATES = Path(__file__).resolve().parents[1] / "ui" / "templates"


def _text(html):
    return " ".join(html.split())


@pytest.fixture
def no_runs(monkeypatch):
    monkeypatch.setattr(ui_shared, "_latest_results", lambda: (None, None))


def _run(monkeypatch, models):
    res = {"forecast_date": "2098-11-14", "observed": {},
           "models": {m: {"Ohio": {"1": {"0.1": 1.0, "0.5": 2.0, "0.9": 3.0}}}
                      for m in models}}
    monkeypatch.setattr(ui_shared, "_latest_results",
                        lambda: ("20981114T093100-abcdef", res))


# ------------------------------------------------------------ the header

def test_header_names_kind_status_and_links_methods():
    for path, kind, status, anchor in (
            ("/models", "Mechanistic", "Submitted to FluSight", "oracle"),
            ("/model/analogue", "Empirical", "Submitted to FluSight",
             "analogue"),
            ("/model/pf2s", "Mechanistic", "Research only", "two-strain")):
        t = client.get(path).text
        hero = t.split('class="card md-hero"', 1)[1].split("</section>", 1)[0]
        assert f'<span class="md-kind">{kind}</span>' in hero, path
        assert f'<span class="uk-badge-t">{status}</span>' in hero, path
        assert f'href="/methods#{anchor}"' in hero, path
        # the full description is in the page, behind a closed fold
        assert '<details class="uk-fold md-about" id="md-about">' in hero


def test_the_record_sentences_ride_the_record_toggletip():
    """The relWIS sentences (the PF card's hint and its tip, the other
    descriptions' last sentence) are word for word in the Record "i"; the
    bars and facts show their numbers."""
    both = ot.RECORD["both"]
    wanted = {
        "/models": (
            ("relWIS vs the FluSight baseline (below 1 beats it): "
             f"{ot.fmt(both['oracle'])} against the plain filter's "
             f"{ot.fmt(both['filter'])} on the same "
             f"{ot.cells(both['cells'])} cells of 2024-25 and 2025-26."),
            ("a frozen-specification replication whose prospective "
             'test is the 2026-27 season (<a href="/methods#oracle">'
             "Methods</a>).")),
        "/model/analogue": (
            ("Three-season relWIS vs the FluSight baseline on "
             "15,340 cells: 0.722, 0.653 and 0.651, pooled "
             "0.666 (0.771 without the FluSurv-NET donors)."),),
        "/model/pf2s": (
            ("It scored worse on the full grid (relWIS 0.719 "
             "against 0.704 for the two-member blend it was "
             "tested in), so it is kept for research runs only."),),
    }
    for path, needles in wanted.items():
        t = client.get(path).text
        pop = _text(t.split('id="tt-md-rec"', 1)[1].split("</span></span>", 1)[0])
        for needle in needles:
            assert needle in pop, (path, needle)
        # one bar per compared score, each value as text beside it
        assert t.count('class="md-bar-track" aria-hidden="true"') == 2, path
    # the one relWIS rule: tabular, ok below 1
    assert '<span class="md-bar-v relwis ok">0.731</span>' in \
        client.get("/models").text
    gh = client.get("/model/analogue").text
    assert re.search(r'uk-stat--ok"><dt>2023-24</dt><dd><span class="uk-stat-v">'
                     r'0\.722</span>', gh)
    pf2s = client.get("/model/pf2s").text
    assert '<span class="uk-badge-t">scored worse</span>' in pf2s


# ------------------------------------------------- equations: kit and plain

def test_model_pages_name_each_equation_and_tip_its_note():
    t = client.get("/models").text
    for name in ("Growth blend", "Growth rate", "Sample rescale",
                 "Seasonal forcing", "Observation model"):
        assert f'<span class="md-eqname">{name}' in t, name
    # the fallback caveat rides the growth blend's tip
    blend = t.split('id="tip-dg-eq-blend"', 1)[1].split("</span></span>", 1)[0]
    assert "A week with too few donors (30 paths per stream)" in _text(blend)
    # the parameter sentence is the fixed row's tip; the chips show both rows
    assert "Fitted per state</dt>" in t
    fixed = t.split('id="tip-dg-eq-fixed"', 1)[1].split("</span></span>", 1)[0]
    assert "(recorded working assumptions)" in fixed
    assert "enters through the accumulator that fills" in fixed
    # the harmonic's caption is a badge with the caption in its tip
    assert '<span class="uk-badge-t">illustrative values</span>' in t
    assert "both are fitted per state and week." in t
    assert 'class="eqnote"' not in t
    p2 = client.get("/model/pf2s").text
    for name in ("Admissions channel", "Strain share channel"):
        assert f'<span class="md-eqname">{name}' in p2, name
    assert "all are fitted per state and week." in p2


def test_methods_home_and_the_site_keep_the_plain_notes():
    """The public site renders Methods without the UI kit: its equation
    notes stay visible text, never a tip."""
    from app.core import site_build
    versions = {k: "x" for k in ("pybnf", "bngsim", "bionetgen", "fastapi",
                                 "plotly")}
    for html in (client.get("/methods").text, client.get("/").text,
                 site_build.harvest_methods(versions)):
        assert 'class="eqnote"' in html
        assert "md-eq" not in html and 'id="tip-dg-' not in html
    assert "Values shown are illustrative" in client.get("/methods").text


# --------------------------------------------------- forecasts card states

def test_no_run_shows_the_empty_state(no_runs):
    t = client.get("/models").text
    fc = t.split('class="card md-fc"', 1)[1]
    assert 'class="uk-empty"' in fc and "No forecasts from this model yet" in fc
    assert "Run details" not in fc


def test_a_run_without_this_model_names_itself_in_the_tip(monkeypatch):
    _run(monkeypatch, ["analogue"])
    t = client.get("/models").text
    assert "No forecasts from this model yet" in t
    assert "The latest run (2098-11-14 · 11-14 09:31) has none from this model." in t


def test_the_latest_run_is_labelled_values_with_its_page_linked(monkeypatch):
    _run(monkeypatch, ["pf", "analogue"])
    t = client.get("/model/analogue").text
    facts = t.split('md-runfacts"', 1)[1].split("</dl>", 1)[0]
    assert "Forecast date" in facts and "2098-11-14" in facts
    assert "11-14 09:31" in facts
    assert 'href="/runs/20981114T093100-abcdef"' in facts
    assert "No forecasts from this model yet" not in t


def test_the_research_view_has_no_forecasts_card_and_links_storage():
    t = client.get("/model/pf2s").text
    assert 'id="mfan"' not in t and 'class="card md-fc"' not in t
    card = t.split('id="research-run"', 1)[1]
    assert 'href="/storage"' in card


# ------------------------------------------------------------- run forms

def _form_fields(html, start):
    form = html.split(start, 1)[1].split("</form>", 1)[0]
    return sorted(set(re.findall(r'name="(\w+)"', form)))


def test_quick_run_posts_the_same_fields_as_before():
    base = ["engine", "forecast_date", "locations", "replicates",
            "weeks_to_drop", "weeks_to_nowcast"]
    for path, engine in (("/models", "pf"), ("/model/analogue", "analogue")):
        t = client.get(path).text
        assert _form_fields(t, 'class="card md-quick"') == base, path
        assert f'name="engine" value="{engine}"' in t, path
    # the Groundhog fits no replicates: the field posts hidden
    gh = client.get("/model/analogue").text
    assert '<input type="hidden" id="mf-reps" name="replicates"' in gh
    assert 'for="mf-reps"' not in gh
    # the format hint is the placeholder; the explanations are label tips
    pf = client.get("/models").text
    assert 'placeholder=\'state names, comma-separated, or "all"\'' in pf
    assert 'title=' not in pf.split('class="card md-quick"', 1)[1].split("</form>", 1)[0]
    for tip in ("tip-md-date", "tip-md-locs", "tip-md-reps"):
        assert f'id="{tip}"' in pf, tip


def test_research_form_fields_are_unchanged():
    t = client.get("/model/pf2s").text
    assert _form_fields(t, 'id="research-run"') == [
        "engine", "forecast_date", "locations", "members", "particles",
        "replicates", "weeks_to_drop", "weeks_to_nowcast"]


def test_a_run_in_progress_is_an_alert_on_the_card_with_the_run_button(
        monkeypatch):
    monkeypatch.setitem(ui_state._status, "running", "r1")
    for path, card in (("/models", 'class="card md-quick"'),
                       ("/model/pf2s", 'id="research-run"')):
        t = client.get(path).text
        body = t.split(card, 1)[1].split("</form>", 1)[0]
        assert 'class="uk-alert uk-alert--warn"' in body, path
        assert "A run is in progress." in body, path
        assert '<a href="/forecast">See the Forecast tab</a>' in body, path
        assert t.count("A run is in progress.") == 1, path


# ----------------------------------------------------------- the page rules

def test_model_pages_print_no_loose_hints():
    """No p.hint paragraph, .pill status or p.warn line is left on the
    tab's pages; the kit carries them."""
    for name in ("model.html", "research_run.html"):
        src = (TEMPLATES / name).read_text()
        assert '<p class="hint"' not in src, name
        assert 'class="pill' not in src, name
        assert '<p class="warn"' not in src, name
    for path in ("/models", "/model/analogue", "/model/pf2s"):
        t = client.get(path).text
        main = t.split('<main id="main"', 1)[1].split("</main>", 1)[0]
        assert '<p class="hint' not in main, path


def test_models_sheet_is_linked_and_scoped():
    t = client.get("/models").text
    assert '<link rel="stylesheet" href="/static/tabs/models.css">' in t
    css = (Path(__file__).resolve().parents[1] / "ui" / "static" / "tabs"
           / "models.css").read_text()
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    for sel in re.findall(r"([^{}]+)\{", body):
        for part in sel.split(","):
            part = part.strip()
            if not part or part.startswith("@") or part in ("from", "to"):
                continue
            # every rule reaches an md- class (never a kit class alone)
            assert "md-" in part, part
