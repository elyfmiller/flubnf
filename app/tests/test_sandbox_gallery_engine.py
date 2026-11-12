"""The Sandbox gallery says before Start what an experiment can do here
(UX review F36, F58, F49, F74, F59, F53, F64 and F17; package P11):

  * without the fitting engine, and where Start does not queue, the model
    page's notice ("This computer cannot fit yet") shows once at the top,
    and Start is off, described by it (no second "?"); with the engine,
    or in a student's folder on the runner computer, neither;
  * each shipped model says what it is; on the public engine the
    two-strain model is listed and cannot be picked (Start's refusal of
    it stays), and a refused pick of it falls back to sihrs;
  * each season says whether a shipped replay is here to compare with
    (the live, archived and imported roots; the runner's in a student's
    folder, nothing when runner.json names none), and its value is the
    bare name, so Start posts what experiments.validate reads;
  * each size says about how long it takes, by the other run forms' rule
    (estimates.span, estimates.human), on this engine or the runner's;
  * a new registration goes on to the Experiments card;
  * the chart library loads only for a run with a trajectory to draw.

The forms are read from the page the server renders: what Start posts is
the form's data set as a browser builds it (served_dom, the markup's
selected and disabled options), not a dict written here.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np                                       # noqa: E402
import pytest                                            # noqa: E402

from app.core import experiments as X                    # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import sandbox as sb                       # noqa: E402
from app.core.engines import pf                          # noqa: E402
from app.ui import pipeline as ui_pipeline               # noqa: E402
from app.ui import retro_seasons as ui_retro_seasons     # noqa: E402
from app.ui import state as ui_state                     # noqa: E402
from app.ui import versions as ui_versions               # noqa: E402

import served_dom as SD                                  # noqa: E402
from test_experiments import (SMOKE_WEEKS, VINTAGES, _on,  # noqa: E402,F401
                              _replay, season, truth)
from test_fewer_marks import marks                       # noqa: E402
from test_runner_folders import students                 # noqa: E402,F401
from test_runner_queue import state as runner_state      # noqa: E402
from test_sandbox_experiments import (_join, _no_console_run,  # noqa: E402
                                      _no_flash, client, world_root)
from test_sandbox_experiments import alice, world        # noqa: E402,F401
from test_sandbox_placeholders import strict_bng         # noqa: E402,F401
from test_sandbox_shipped import FD, hub                 # noqa: E402,F401

#: subprocess.run as it is before any fixture fakes it
REAL_RUN = subprocess.run
needs_js = pytest.mark.skipif(
    not SD.HAVE_JS, reason="no JavaScript engine (JavaScriptCore jsc or node)")

#: the gallery's Experiments form as a browser reads it from the served
#: markup: each select's options (value, text, selected, disabled), Start,
#: and the form's data set (HTML's rules: a select posts its last selected
#: option, else its first enabled one, and never a disabled option), with
#: choose(name, value) picking an option first as a user would
PAGE_JS = r"""
var form = document.querySelector('form[action="/sandbox/experiments"]');
// an element's text, its descendants' included
function txt(el) {
  var s = '';
  el.childNodes.forEach(function (c) { s += c.nodeType === 3 ? c.data : txt(c); });
  return s;
}
function opts(s) {
  return s.options.map(function (o) {
    var g = o.parentNode;
    return {value: o.value, text: txt(o), selected: o.selected,
            disabled: o.disabled || (g.localName === 'optgroup' && g.disabled)};
  });
}
function data() {
  var out = {}, sels = form.querySelectorAll('select');
  for (var i = 0; i < sels.length; i++) {
    var s = sels[i], o = opts(s), pick = null;
    if (!s.getAttribute('name') || s.disabled) continue;
    for (var j = 0; j < o.length; j++) if (o[j].selected) pick = o[j];
    if (!pick) for (j = 0; j < o.length; j++) if (!o[j].disabled) { pick = o[j]; break; }
    if (pick && !pick.disabled) out[s.getAttribute('name')] = pick.value;
  }
  return out;
}
function choose(name, value) {
  var s = form.querySelector('select[name=' + name + ']'), hit = false;
  s.options.forEach(function (o) {
    var on = o.value === value && !opts(s)[s.options.indexOf(o)].disabled;
    o.selected = on; if (on) hit = true;
  });
  return hit;
}
function state() {
  if (!form) return null;
  var start = form.querySelector('button'), why = start.getAttribute('aria-describedby'),
      alert = document.getElementById('sb-machine'), sels = {};
  form.querySelectorAll('select').forEach(function (s) { sels[s.id] = opts(s); });
  return {selects: sels, data: data(), start: {
            text: txt(start), disabled: start.disabled,
            guard: start.getAttribute('data-guard'), describedby: why,
            reason: why && document.getElementById(why)
                      ? txt(document.getElementById(why)) : null},
          alert: alert ? txt(alert).replace(/\s+/g, ' ') : null};
}
"""


def _page(tmp_path, html: str, body: str = "return state();"):
    """What the served page's Experiments form shows and posts. The
    fixtures' BNG2.pl fakes stand in for subprocess.run itself, so the
    JavaScript engine is started with the real one."""
    faked, subprocess.run = subprocess.run, REAL_RUN
    try:
        return SD.run(tmp_path / "js", html, [], PAGE_JS + body)
    finally:
        subprocess.run = faked


def _texts(got: dict, sel: str) -> list:
    return [o["text"] for o in got["selects"][sel]]


def _gallery(tmp_path, body: str = "return state();"):
    r = client.get("/sandbox")
    assert r.status_code == 200
    return r.text, _page(tmp_path, r.text, body)


@pytest.fixture(autouse=True)
def _no_update_notice(monkeypatch):
    """The fixtures' BNG2.pl fakes stand in for every process, git's too
    (versions._repo_sha), and the update notice keeps that answer for 10
    s, which would reach the next module's pages: here the build on disk
    is the one running."""
    monkeypatch.setattr(ui_versions, "_repo_sha_on_disk",
                        lambda: ui_versions.RUNNING_SHA)


def _replays_held(monkeypatch) -> list:
    """experiments.replay faked: what each start would have replayed."""
    seen = []

    def replay(settings, *, retro_root, cancelled=None):
        seen.append(dict(settings))
    monkeypatch.setattr(X, "replay", replay)
    return seen


# ------------------------------------------- F36: the engine, said once

@needs_js
def test_without_the_engine_the_notice_shows_once_and_start_is_off(
        world, tmp_path, monkeypatch):
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "absent")
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    html, got = _gallery(tmp_path)
    # the model page's own notice and words, once, at the top
    notice, tip = sb.split_reason(sb.machine_problem())
    assert notice and html.count('id="sb-machine"') == 1
    assert got["alert"].startswith("This computer cannot fit yet: " + notice)
    assert html.index('id="sb-machine"') < html.index('id="h-sb-new"')
    # Start is off, described by that notice: no guard, no "?" of its own
    start = got["start"]
    assert (start["text"], start["disabled"], start["guard"],
            start["describedby"]) == ("Start", True, None, "sb-machine")
    assert " ".join(start["reason"].split()).startswith(
        "This computer cannot fit yet: " + notice)
    card = html[html.index('<h2 id="h-sb-exp">'):
                html.index("window.SANDBOX_RES")]
    assert marks(card) == []
    assert marks(html).count("tip-sb-machine") == (1 if tip else 0)
    # the choices still read as they would
    assert got["data"]["model"] == "sihrs"


@needs_js
def test_an_engine_its_pieces_disagree_on_says_the_experiments_words(
        world, tmp_path, monkeypatch):
    """The suite's own case: the stub fork is there (machine_problem
    names nothing) while the engine's venv is not (the state is absent):
    the experiment's own refusal words say why."""
    monkeypatch.setattr(ui_pipeline, "_pf_engine_state", lambda: "absent")
    assert sb.machine_problem() == ""
    html, got = _gallery(tmp_path)
    assert got["alert"].startswith(
        "This computer cannot fit yet: An experiment needs the fitting "
        "engine, which is not installed on this machine.")
    assert got["start"]["disabled"] and got["start"]["describedby"] == \
        "sb-machine"


@needs_js
def test_with_the_engine_no_notice_and_start_is_on(world, tmp_path):
    html, got = _gallery(tmp_path)
    assert got["alert"] is None and 'id="sb-machine"' not in html
    assert got["start"] == {"text": "Start", "disabled": False,
                            "guard": "sandbox-run", "describedby": None,
                            "reason": None}


@needs_js
def test_in_a_runner_folder_start_queues_and_no_engine_is_asked(
        alice, tmp_path, monkeypatch):
    _no_console_run(monkeypatch)            # _pf_engine_state raises
    monkeypatch.setattr(pf, "engine_available", lambda: False)
    html, got = _gallery(tmp_path)
    assert got["alert"] is None and 'id="sb-machine"' not in html
    assert got["start"] == {"text": "Start", "disabled": False,
                            "guard": None, "describedby": None,
                            "reason": None}


# ------------------------------------- F58, F49, F74: the model's words

@needs_js
def test_on_the_public_engine_the_two_strain_model_cannot_be_picked(
        world, tmp_path, monkeypatch):
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    seen = _replays_held(monkeypatch)
    # private: all three, each saying what it is
    _html, got = _gallery(tmp_path)
    assert [(o["value"], o["text"], o["disabled"])
            for o in got["selects"]["sbexp-model"]] == [
        ("sihrs", "sihrs · the Oracle SIHRS, as shipped", False),
        ("sihrs-2strain", "sihrs-2strain · influenza A and B (research)",
         False),
        ("sihrs-natg", "sihrs-natg · with a national-growth factor "
         "(research)", False)]
    assert _texts(got, "sbexp-oracle") == ["on",
                                           "off (the Liu-West filter alone)"]
    # public: listed, said, and not pickable
    _on(monkeypatch, tmp_path, "public")
    _html, got = _gallery(tmp_path, "return [state(), choose('model', "
                                    "'sihrs-2strain'), data()];")
    got, picked, posted = got
    two = got["selects"]["sbexp-model"][1]
    assert (two["value"], two["text"], two["disabled"]) == (
        "sihrs-2strain", "sihrs-2strain · influenza A and B (research) · "
        "private engine only", True)
    assert not got["selects"]["sbexp-model"][2]["disabled"]
    assert picked is False and posted["model"] == "sihrs"
    # Start's refusal of it stays (a script, or an old page, posting it)
    _no_flash()
    r = client.post("/sandbox/experiments",
                    data={"model": "sihrs-2strain", "season": "2024-25",
                          "oracle": "off"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/sandbox"
    said = ((ui_state._status.get("flash") or "") + " "
            + (ui_state._status.get("flash_detail") or ""))
    assert said.startswith("Not started: sihrs-2strain runs on the private "
                           "engine only") and "(MACHINE)" in said
    assert seen == []
    # the refused form comes back on sihrs, with its Oracle step on
    _html, got = _gallery(tmp_path)
    assert got["data"]["model"] == "sihrs" and got["data"]["oracle"] == "on"
    assert [o["value"] for o in got["selects"]["sbexp-model"]
            if o["selected"]] == ["sihrs"]


# --------------------------------------------------- F59: the seasons

def calendars(monkeypatch, *seasons) -> dict:
    """test_experiments.season's 2024-25 calendar moved to each of
    `seasons` by whole years of weeks (each week keeps its parity), so a
    plan of any of them has weeks: {season: its smoke weeks}."""
    from datetime import date, timedelta

    from app.core import runner

    def moved(s):
        shift = timedelta(weeks=52 * (int(s[:4]) - 2024))
        return [(date.fromisoformat(v) + shift).isoformat() for v in VINTAGES]
    monkeypatch.setattr(retro, "season_vintages",
                        lambda s: moved(s) if s in seasons else [])
    return {s: runner._plan_weeks({"season": s, "size": "smoke"})
            for s in seasons}


@needs_js
def test_each_season_says_whether_a_shipped_replay_is_here(
        world, tmp_path, monkeypatch):
    monkeypatch.setattr(retro, "available_seasons",
                        lambda: ["2022-23", "2023-24", "2024-25"])
    smoke = calendars(monkeypatch, "2022-23", "2023-24", "2024-25")
    assert smoke["2024-25"] == SMOKE_WEEKS
    root = world_root()
    # 2024-25: the shipped replay, live; 2023-24: only an archived (or
    # imported: the same <season>__archived_<stamp> root) one;
    # 2022-23: the Groundhog alone, which is not the shipped replay
    _replay(root / "2024-25", weeks=SMOKE_WEEKS)
    _replay(root / "2023-24__archived_20260101T000000Z",
            weeks=smoke["2023-24"])
    _replay(root / "2022-23", engine="analogue", weeks=smoke["2022-23"])
    _html, got = _gallery(tmp_path)
    seasons = got["selects"]["sbexp-season"]
    assert [(o["value"], o["text"]) for o in seasons] == [
        ("2024-25", "2024-25 · shipped replay here"),
        ("2023-24", "2023-24 · shipped replay here"),
        ("2022-23", "2022-23 · nothing to compare with")]
    assert got["data"]["season"] == "2024-25"
    # the words never move the pick: experiments.default_season's, the
    # newest live root with the shipped replay, else the newest season
    # (origin/dev's), so an untouched Start posts what it posted there
    shutil.rmtree(root / "2024-25")
    _html, got = _gallery(tmp_path)
    assert [o["text"] for o in got["selects"]["sbexp-season"]][:2] == [
        "2024-25 · nothing to compare with",
        "2023-24 · shipped replay here"]
    assert got["data"]["season"] == "2024-25" == X.default_season(root)


@needs_js
def test_start_posts_each_choice_by_its_value(world, tmp_path, monkeypatch):
    """The season's words ride beside its name: what Start posts is the
    bare name (an option without a value attribute posts its text, which
    experiments.validate refuses), and each size and Oracle step choice
    starts as the form names it."""
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    seen = _replays_held(monkeypatch)
    html = client.get("/sandbox").text
    started = []
    for size in ("smoke", "pilot"):
        for oracle in ("on", "off"):
            posted = _page(tmp_path, html,
                           f"choose('size', '{size}'); "
                           f"choose('oracle', '{oracle}'); return data();")
            assert posted == {"model": "sihrs", "season": "2024-25",
                              "size": size, "oracle": oracle}, posted
            _no_flash()
            r = client.post("/sandbox/experiments", data=posted,
                            follow_redirects=False)
            assert r.status_code == 303, r.text[:200]
            eid = X.experiment_id(X.read({**posted,
                                          "oracle": oracle == "on"}))
            assert r.headers["location"] == f"/sandbox/experiments/{eid}"
            assert (ui_state._status.get("flash") or "").startswith(
                f"Started {eid}"), ui_state._status.get("flash")
            _join()
            started.append(eid)
    assert started == ["sihrs_2024-25_smoke_oracle", "sihrs_2024-25_smoke",
                       "sihrs_2024-25_pilot_oracle", "sihrs_2024-25_pilot"]
    assert [s["season"] for s in seen] == ["2024-25"] * 4


@needs_js
def test_in_a_runner_folder_the_seasons_are_the_runners(
        alice, students, tmp_path, monkeypatch):
    monkeypatch.setattr(retro, "available_seasons",
                        lambda: ["2023-24", "2024-25"])
    smoke = calendars(monkeypatch, "2023-24", "2024-25")
    # the runner's retro root holds 2023-24's shipped replay; this
    # console's own holds 2024-25's, which the runner does not see
    theirs = tmp_path / "runner-retro"
    _replay(theirs / "2023-24", weeks=smoke["2023-24"])
    _replay(world_root() / "2024-25", weeks=SMOKE_WEEKS)
    runner_state(students, retro_root=str(theirs))
    _html, got = _gallery(tmp_path)
    assert [o["text"] for o in got["selects"]["sbexp-season"]] == [
        "2024-25 · nothing to compare with",
        "2023-24 · shipped replay here"]
    # the words are the runner's; the pick is still origin/dev's
    # (experiments.default_season of this console's own roots)
    assert got["data"]["season"] == "2024-25"
    # a runner.json that names no retro root: nothing said
    runner_state(students)
    _html, got = _gallery(tmp_path)
    assert [o["text"] for o in got["selects"]["sbexp-season"]] == [
        "2024-25", "2023-24"]


# ------------------------------------------------------ F53: the sizes

def _sizes(tmp_path) -> list:
    _html, got = _gallery(tmp_path)
    return _texts(got, "sbexp-size")


@needs_js
def test_each_size_says_how_long_by_the_other_forms_rule(
        world, tmp_path, monkeypatch):
    # cost_pinned (the world's): 30 s a fit, 8 runners, the first
    # estimate 1 to 4 times the model, no recorded pace
    assert _sizes(tmp_path) == [
        "smoke: 2 locations, 2 weeks (about 1 to 4 min)",
        "pilot: 10 locations, every other week (about 14 to 56 min)",
        "full: every location and week, as shipped (about 5.0 to 20.0 h)"]
    # the same figure as the Retrospective's rule: estimates over the
    # weeks a plan freezes
    from app.core import estimates, runner
    weeks = runner._plan_weeks(X.read({"model": "sihrs",
                                       "season": "2024-25"}))
    start = retro.season_bounds("2024-25")[0]
    secs = estimates.run_seconds(
        [estimates.n_obs_for(w, start) for w in weeks], 2, 10_000, 8)
    assert secs == 60.0 and estimates.human(*estimates.span(secs)) == \
        "about 1 to 4 min"
    # this computer's recorded pace: one figure, "here"
    monkeypatch.setattr(ui_retro_seasons, "_own_cost_ratio",
                        lambda: (2.0, 5))
    assert _sizes(tmp_path)[0] == "smoke: 2 locations, 2 weeks (about 2 min here)"
    # the public engine prices its 2.4 times the private one
    monkeypatch.setattr(ui_retro_seasons, "_own_cost_ratio",
                        lambda: (None, 0))
    _on(monkeypatch, tmp_path, "public")
    assert _sizes(tmp_path)[0] == "smoke: 2 locations, 2 weeks (about 2 to 10 min)"


@needs_js
def test_a_season_no_plan_can_freeze_gives_no_time_and_keeps_the_card(
        world, tmp_path, monkeypatch):
    for asked, code in (("2031-32", "SEASON_NO_WEEKS"),
                        ("autumn", "SEASON_NO_WEEKS")):
        _no_flash()
        r = client.post("/sandbox/experiments",
                        data={"model": "sihrs", "season": asked,
                              "size": "pilot"}, follow_redirects=False)
        assert r.status_code == 303
        assert (ui_state._status.get("flash") or "").endswith(f"({code}).")
        _html, got = _gallery(tmp_path)
        assert _texts(got, "sbexp-size") == [
            "smoke: 2 locations, 2 weeks",
            "pilot: 10 locations, every other week",
            "full: every location and week, as shipped"], asked
        assert got["start"]["text"] == "Start"


@needs_js
def test_in_a_runner_folder_the_sizes_are_the_runners(
        alice, students, tmp_path, monkeypatch):
    # runner.json naming its engine: the first estimate, on the runner
    runner_state(students, retro_root=str(world_root()), engine="public")
    assert _sizes(tmp_path)[0] == (
        "smoke: 2 locations, 2 weeks (about 2 to 10 min on the runner)")
    # its smokes timed there: their k, one figure (the pilot's first
    # estimate at the Mac Studio's 16 runners: one wave a week)
    runner_state(students, retro_root=str(world_root()), engine="private",
                 recent=[{"folder": "bob", "id": "x", "size": "smoke",
                          "kind": "run", "outcome": "done", "weeks": 2,
                          "k": 3.0}])
    assert _sizes(tmp_path)[:2] == [
        "smoke: 2 locations, 2 weeks (about 3 min on the runner)",
        "pilot: 10 locations, every other week (about 7 to 28 min on the "
        "runner)"]
    # none named (an older runner): no time
    runner_state(students, retro_root=str(world_root()))
    assert _sizes(tmp_path)[0] == "smoke: 2 locations, 2 weeks"


# --------------------------------------------- F64: on to Experiments

@needs_js
def test_a_new_registration_opens_the_experiments_card_on_it(
        strict_bng, hub, tmp_path):
    sb.from_shipped("beta", "Alabama", FD, template=True)
    r = client.post("/sandbox/models/beta/register", data={},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/sandbox#h-sb-exp"
    page, frag = r.headers["location"].split("#")
    html = client.get(page).text
    got = _page(tmp_path, html, "return [state(), "
                "!!document.getElementById('" + frag + "')];")
    assert got[1] is True                          # the card is there
    assert got[0]["data"]["model"] == "beta@1"     # and picks it
    assert [o["text"] for o in got[0]["selects"]["sbexp-model"]
            if o["selected"]][0].startswith("beta@1 · ")


# ------------------------------------------ F17: the chart library

def _trajectory_run(monkeypatch) -> str:
    """A finished fit of kinetics_example (already added) with a
    trajectory (the engine faked, as test_sandbox.py fakes it); its id."""
    w = sb.prepare("kinetics_example", particles=100)
    cell = w / "kinetics_example_r0"

    def fake_execute(workroot, width=None, timeout=None, env=None):
        runs = cell / "out" / "Results" / "PF" / "Runs"
        runs.mkdir(parents=True)
        tr = np.tile(np.arange(1.0, 17.0), (100, 1))
        np.savetxt(runs / "traj_noise_kinB_weekly_chain_0.txt", tr)
        return {"kinetics_example_r0": "ok"}
    monkeypatch.setattr(sb.pf_engine, "execute", fake_execute)
    assert sb.run(w)["status"] == "ok"
    return w.name


def _head_scripts(html: str) -> list:
    head = html.split("</head>", 1)[0]
    return re.findall(r'<script(?: defer)? src="/static/([^"]+)"', head)


def test_the_chart_library_loads_only_for_a_trajectory(sandbox_root,
                                                       monkeypatch):
    gallery = client.get("/sandbox").text
    assert "plotly.min.js" not in gallery and "charts.js" not in gallery
    sb.add_example("kinetics_example")
    page = client.get("/sandbox?model=kinetics_example").text
    assert "plotly.min.js" not in page and 'id="sbplot"' not in page
    rid = _trajectory_run(monkeypatch)
    page = client.get(f"/sandbox?model=kinetics_example&run={rid}").text
    # Plotly and the chart helper load (in order, not deferred) before
    # sandbox.js, whose plot() draws #sbplot from the run's trajectory
    scripts = _head_scripts(page)
    assert scripts.index("plotly.min.js") < scripts.index("charts.js") \
        < scripts.index("sandbox.js")
    assert '<script src="/static/plotly.min.js"></script>' in page
    assert 'id="sbplot"' in page
    res = json.loads(page.split("window.SANDBOX_RES = ", 1)[1].split(
        "; window.SANDBOX_CMP", 1)[0])
    assert res["traj"]["q50"][:3] == [1.0, 2.0, 3.0]
