"""The Sandbox gallery's Experiments card against what the server does
(review 3 of #93, part 2: P2-1, P2-2, P2-4 and P2-6):

  * P2-1: with the engine not ready, opening the gallery makes no folder
    and starts no process (no runs folder, no BNG2.pl self-test, no
    engine probe): its notice comes from files only;
  * P2-2: the season an untouched Start posts is experiments.
    default_season's, as on origin/dev; the seasons' words never move it;
  * P2-4: Start is off for want of the engine only where the server
    would refuse for that: a choice that is a complete experiment is
    answered first ("is complete", its page), so Start stays on for it,
    and the two-strain model with a complete experiment can be picked on
    the public engine;
  * P2-6: "shipped replay here" by the comparison's own test
    (experiments.reference: the shipped forecasts in a planned week).
"""
import json
import re
import shutil
import subprocess
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import library as L                        # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.ui import pipeline as ui_pipeline               # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui import versions as ui_versions               # noqa: E402
from app.ui.routes import sandbox as ui_sandbox          # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_experiment_summary import _store               # noqa: E402
from test_experiments import (SMOKE_WEEKS, _on, _replay,  # noqa: E402,F401
                              season, truth)
from test_sandbox_experiments import (_no_flash, _options,  # noqa: E402
                                      client, world_root)
from test_sandbox_experiments import world               # noqa: E402,F401
from test_sandbox_gallery_engine import (PAGE_JS, REAL_RUN,  # noqa: E402
                                         calendars, needs_js)

#: the probes as written (sandbox_root answers "ready" for both)
REAL_IMPORT_PROBLEM = sb.engine_import_problem
REAL_BNG_PROBLEM = sb.bng_problem


@pytest.fixture(autouse=True)
def _no_update_notice(monkeypatch):
    """The build on disk is the one running: no git process for the
    update notice (versions._repo_sha)."""
    monkeypatch.setattr(ui_versions, "_repo_sha_on_disk",
                        lambda: ui_versions.RUNNING_SHA)


def _selected(html: str, select_id: str) -> list:
    """The values of a select's selected options in the served markup."""
    return [re.search(r'value="([^"]*)"', a).group(1)
            for a, _t in _options(html, select_id) if " selected" in a]


def _start(html: str) -> str:
    """The Experiments form's Start button's attributes as served."""
    form = html.split('<form method="post" action="/sandbox/experiments">',
                      1)[1].split("</form>", 1)[0]
    return re.search(r"<button([^>]*)>Start</button>", form).group(1)


def _absent(monkeypatch) -> None:
    """No fitting engine here, as the pages read it."""
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "absent")
    monkeypatch.setattr(pf, "engine_available", lambda: False)


def _complete(settings: dict) -> Path:
    """An experiment every week of whose plan is stored: complete."""
    s = X.read(settings)
    folder = X.root() / X.experiment_id(s)
    folder.mkdir(parents=True)
    L.write_json(folder / X.SETTINGS, json.loads(X.settings_text(s)))
    weeks = runner._plan_weeks(s)
    retro.write_meta(folder, {
        "status": "done", "started_utc": 1_790_000_000.0,
        "finished_utc": 1_790_000_100.0, "elapsed_s": 100.0,
        "settings": {"experiment": "e" * 64, "model": s["model"],
                     "weeks": weeks, "locations": ["California", "Vermont"],
                     "replicates": 1, "particles": 10_000}})
    for w in weeks:
        _store(folder, w, {"pf": {"Vermont": {"0": {0.5: 3.0}}}})
    assert weeks and X.status(folder)["complete"]
    return folder


# ------------------------------------- P2-1: no folder, no process

@pytest.fixture
def counted(sandbox_root, tmp_path, monkeypatch):
    """sandbox_root (its folder not made yet) with the real engine-import
    probe and BNG2.pl checks, a BNG2.pl file there, nothing remembered,
    and every probe a process would start counted (a list of argv)."""
    monkeypatch.setattr(sb, "engine_import_problem", REAL_IMPORT_PROBLEM)
    monkeypatch.setattr(sb, "bng_problem", REAL_BNG_PROBLEM)
    monkeypatch.setattr(sb, "_ENGINE_PROBES", {})
    monkeypatch.setattr(sb, "_BNG_SELFTESTS", {})
    bng = tmp_path / "bng" / "BNG2.pl"
    bng.parent.mkdir()
    bng.write_text("# stub\n")
    monkeypatch.setattr(sb, "BNG", str(bng))
    monkeypatch.setattr(pf, "resolve_perl", lambda *a, **k: "perl")
    monkeypatch.setattr(sb, "bng_env", lambda *a, **k: None)
    calls = []

    def probe(cmd, **kw):
        calls.append(list(cmd))
        return types.SimpleNamespace(returncode=0, stderr="",
                                     stdout="BioNetGen version 2.9.3\n")
    monkeypatch.setattr(sb, "_probe_run", probe)
    assert not sb.SANDBOX.exists()
    return calls


def test_an_engineless_gallery_makes_no_folder_and_starts_no_process(
        counted, monkeypatch):
    _absent(monkeypatch)
    for _ in range(2):
        r = client.get("/sandbox")
        assert r.status_code == 200
        html = r.text
        # the notice still says why, once: the model page's first reason
        assert html.count('id="sb-machine"') == 1
        assert ("This computer cannot fit yet:</strong> The fitting engine "
                "is not installed.") in html
    assert counted == [] and sb._BNG_SELFTESTS == {}
    assert not sb.SANDBOX.exists(), sorted(
        str(p) for p in sb.SANDBOX.rglob("*"))
    # the model page's own look is unchanged: it makes the runs folder
    # and runs the self-test, as before
    assert sb.machine_problem().startswith(
        "The fitting engine is not installed. ")
    assert sb.RUNS.is_dir() and [c[-1] for c in counted] == ["-v"]


def test_an_engine_its_pieces_disagree_on_starts_no_probe_either(
        counted, monkeypatch):
    """The engine there (the fork's filter) and the state not ready: the
    model page's look would start the engine-import probe and the
    self-test; the gallery says the experiment's words from files."""
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "absent")
    monkeypatch.setattr(pf, "engine_available", lambda: True)
    monkeypatch.setattr(pf, "engine_current", lambda: True)
    html = client.get("/sandbox").text
    assert ("This computer cannot fit yet:</strong> An experiment needs the "
            "fitting engine, ") in html
    assert counted == [] and sb._ENGINE_PROBES == {}
    assert not sb.SANDBOX.exists()


# --------------------------------- P2-2: the season Start posts

def test_an_untouched_start_posts_the_season_origin_dev_picks(
        world, monkeypatch):
    """Two seasons, no live shipped replay, an archived one of 2023-24:
    origin/dev picks 2024-25 (default_season reads the live roots only);
    so does this card, whatever its words say."""
    monkeypatch.setattr(retro, "available_seasons",
                        lambda: ["2023-24", "2024-25"])
    smoke = calendars(monkeypatch, "2023-24", "2024-25")
    root = world_root()
    _replay(root / "2023-24__archived_20260101T000000Z",
            weeks=smoke["2023-24"])
    html = client.get("/sandbox").text
    texts = [t for _a, t in _options(html, "sbexp-season")]
    assert texts == ["2024-25 · nothing to compare with",
                     "2023-24 · shipped replay here"]
    assert _selected(html, "sbexp-season") == ["2024-25"] == [
        X.default_season(root)]
    # a live shipped replay of 2023-24 moves it, as it moves default_season
    _replay(root / "2023-24", weeks=smoke["2023-24"])
    html = client.get("/sandbox").text
    assert _selected(html, "sbexp-season") == ["2023-24"] == [
        X.default_season(root)]


# ------------------------------- P2-6: "shipped replay here", by reference

def test_a_season_is_labelled_by_the_comparisons_own_test(world,
                                                         monkeypatch):
    monkeypatch.setattr(retro, "available_seasons", lambda: ["2024-25"])
    root = world_root() / "2024-25"

    def notes() -> dict:
        return ui_sandbox._season_notes(world_root(), ["2024-25"])

    def week_label() -> str:
        html = client.get("/sandbox").text
        return [t for _a, t in _options(html, "sbexp-season")][0]
    # a shipped record with no week stored: nothing to compare with (it
    # was "shipped replay here" by the record alone)
    retro.write_meta(root, {"started_utc": 1_790_000_000.0,
                            "settings": dict(X.SHIPPED_SETTINGS)})
    assert X._shipped(retro.read_meta(root))
    assert X.reference(world_root(), "2024-25", True, SMOKE_WEEKS) is None
    assert notes() == {"2024-25": ui_sandbox.SEASON_NONE}
    assert week_label() == "2024-25 · nothing to compare with"
    # weeks stored outside the smoke plan: a pilot compares, a smoke
    # does not
    pilot_only = [w for w in runner._plan_weeks(
        {"season": "2024-25", "size": "pilot"}) if w not in SMOKE_WEEKS]
    _replay(root, weeks=pilot_only[:1])
    assert X.reference(world_root(), "2024-25", True, SMOKE_WEEKS) is None
    assert week_label() == "2024-25 · part of a shipped replay here"
    # the smoke plan's weeks with the Oracle step's forecasts only (no
    # Liu-West filter's): still part
    shutil.rmtree(root)
    _replay(root, weeks=SMOKE_WEEKS, filter_=False)
    assert X.reference(world_root(), "2024-25", True, SMOKE_WEEKS)
    assert X.reference(world_root(), "2024-25", False, SMOKE_WEEKS) is None
    assert week_label() == "2024-25 · part of a shipped replay here"
    # both, in the smoke plan's weeks (inside every larger plan): every
    # choice compares
    shutil.rmtree(root)
    _replay(root, weeks=SMOKE_WEEKS)
    assert week_label() == "2024-25 · shipped replay here"


# ------------------- P2-4: Start as the server answers it, complete first

def _script(html: str) -> str:
    return re.search(r'<script id="sbexp-start-js">(.*?)</script>', html,
                     re.S).group(1)


def _run_js(tmp_path, html: str, body: str):
    """The served Experiments form with the page's own Start script run
    (as the browser runs it, where it stands), then `body`."""
    faked, subprocess.run = subprocess.run, REAL_RUN
    try:
        return SD.run(tmp_path / "js", html, [], PAGE_JS + body,
                      prelude=_script(html))
    finally:
        subprocess.run = faked


def test_without_the_engine_start_stays_on_for_a_complete_experiment(
        world, tmp_path, monkeypatch):
    _absent(monkeypatch)
    _complete({"model": "sihrs", "season": "2024-25"})
    html = client.get("/sandbox").text
    assert html.count('id="sb-machine"') == 1
    # the untouched choice is that experiment: Start is on (no guard: the
    # server answers it before any run is asked for)
    attrs = _start(html)
    assert "disabled" not in attrs and "aria-describedby" not in attrs
    assert "data-guard" not in attrs
    assert json.loads(re.search(r"data-complete='([^']*)'", attrs).group(1)
                      ) == ["sihrs|2024-25|smoke|on"]
    # and the server answers it: its page, "is complete", nothing claimed
    _no_flash()
    r = client.post("/sandbox/experiments",
                    data={"model": "sihrs", "season": "2024-25",
                          "size": "smoke", "oracle": "on"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == \
        "/sandbox/experiments/sihrs_2024-25_smoke_oracle"
    assert (ui_state._status.get("flash") or "").startswith(
        "sihrs_2024-25_smoke_oracle is complete")
    # any other choice is refused for the engine: Start is off there
    _no_flash()
    r = client.post("/sandbox/experiments",
                    data={"model": "sihrs", "season": "2024-25",
                          "size": "pilot", "oracle": "on"},
                    follow_redirects=False)
    assert r.headers["location"] == "/sandbox"
    assert "particle-filter engine" in (ui_state._status.get("flash") or "")


@needs_js
def test_start_follows_the_choices_as_the_server_would_answer(
        world, tmp_path, monkeypatch):
    _absent(monkeypatch)
    _complete({"model": "sihrs", "season": "2024-25"})
    html = client.get("/sandbox").text
    got = _run_js(tmp_path, html, """
      var sel = function (n) { return form.querySelector('select[name=' + n + ']'); };
      var seen = [state().start];
      choose('size', 'pilot'); sel('size').fire('change');
      seen.push(state().start);
      choose('size', 'smoke'); sel('size').fire('change');
      seen.push(state().start);
      choose('oracle', 'off'); sel('oracle').fire('change');
      seen.push(state().start);
      return seen;""")
    on, off = [(s["disabled"], s["describedby"]) for s in (got[0], got[1])]
    assert on == (False, None)
    assert off == (True, "sb-machine")
    assert " ".join(got[1]["reason"].split()).startswith(
        "This computer cannot fit yet: The fitting engine is not installed.")
    assert (got[2]["disabled"], got[2]["describedby"]) == (False, None)
    assert (got[3]["disabled"], got[3]["describedby"]) == (True, "sb-machine")
    # with no complete experiment the served page has Start off already
    shutil.rmtree(X.root() / "sihrs_2024-25_smoke_oracle")
    html = client.get("/sandbox").text
    attrs = _start(html)
    assert ' disabled aria-describedby="sb-machine"' in attrs
    got = _run_js(tmp_path, html, "return state().start;")
    assert (got["disabled"], got["describedby"]) == (True, "sb-machine")


def test_on_the_public_engine_a_complete_two_strain_experiment_can_be_picked(
        world, tmp_path, monkeypatch):
    _on(monkeypatch, tmp_path, "public")
    _complete({"model": "sihrs-2strain", "season": "2024-25"})
    html = client.get("/sandbox").text
    two = [a for a, t in _options(html, "sbexp-model")
           if 'value="sihrs-2strain"' in a][0]
    assert " disabled" not in two
    # the server answers it first: its page
    _no_flash()
    r = client.post("/sandbox/experiments",
                    data={"model": "sihrs-2strain", "season": "2024-25",
                          "oracle": "off"}, follow_redirects=False)
    assert r.headers["location"] == \
        "/sandbox/experiments/sihrs-2strain_2024-25_smoke"
    assert (ui_state._status.get("flash") or "").startswith(
        "sihrs-2strain_2024-25_smoke is complete")
    # with none complete it cannot be picked, as before
    shutil.rmtree(X.root() / "sihrs-2strain_2024-25_smoke")
    html = client.get("/sandbox").text
    two = [a for a, t in _options(html, "sbexp-model")
           if 'value="sihrs-2strain"' in a][0]
    assert " disabled" in two
