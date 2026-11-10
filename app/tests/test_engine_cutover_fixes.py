"""The engine cutover's review fixes in the Python core and the UI text:
the runner's job child runs the engine runner.json names, even after the
install is switched while the runner runs; a season whose build cannot be
read records its engine, so a resume on the other engine is refused and
names the right one; the private remedy on a Mac names SetupEngine.command
only where a double-click installs the private engine; a student's
experiment begun on the other engine is told to delete it (it has no
archive); a Sandbox comparison names two engines; the data.exp tip holds on
either engine; a research run's skipped two-strain member is shown; and the
Windows record read after a @. No engine is installed and no process is
started."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402
from fastapi.testclient import TestClient                # noqa: E402

import flubnf.settings as fs                             # noqa: E402
from app.core import engine_build as EB                  # noqa: E402
from app.core import experiments as X                    # noqa: E402
from app.core import retro                               # noqa: E402
from app.core import runner                              # noqa: E402
from app.core import runs                                # noqa: E402
from app.core import sandbox_export as SE                # noqa: E402
from app.ui import server as srv                         # noqa: E402
# fixtures and helpers of the suites these behaviors live in
from test_experiments import _refused, _weeks_run, season  # noqa: E402,F401
from test_runner_folders import students                 # noqa: E402,F401
from test_runner_serve import (POSIX, _job, _private_install,  # noqa: E402
                               ends, world)              # noqa: F401

client = TestClient(srv.app)

PRIVATE = {"branch": "feature/particle-filter", "commit": "2fdadee0",
           "dirty": False, "source": "git", "path": "/x/PyBNF-pf"}
PUBLIC = {"branch": "lanl/PyBNF", "commit": "8410f794", "dirty": False,
          "source": "wheel", "path": "/v/bin/python", "engine": "public"}
#: lwf.public_build when its probe timed out: the engine, no commit
PUBLIC_UNREAD = {"branch": "", "commit": "", "dirty": False,
                 "source": "unknown", "path": "/v/bin/python",
                 "engine": "public",
                 "error": "TimeoutExpired: the probe took over 120 s"}


# ------------------------------------------- the runner's child (review #3)

@POSIX
@pytest.mark.parametrize("raw, engine", [(None, "private"),
                                         (' "Private" ', "private"),
                                         ("pubic", "public")])
def test_the_job_child_runs_the_engine_runner_json_names(
        world, monkeypatch, tmp_path, raw, engine):  # noqa: F811
    """A runner started from a Terminal that names no engine on a copy
    that records private (or one whose Terminal names an engine): its
    child is given that engine, as runner.json says, and keeps it after
    ./setup_engine.sh --public rewrites the record while the runner runs.
    A child reading the record itself would run the public engine under a
    runner that reports private."""
    from app.core.engines import pf
    install = _private_install(tmp_path, monkeypatch)
    monkeypatch.setattr(pf, "engine_current", lambda: True)  # no venv probe
    monkeypatch.setenv("FLUBNF_PY_ENGINE_PUBLIC",
                       str(tmp_path / "public" / "bin" / "python"))
    if raw is None:
        monkeypatch.delenv("FLUBNF_ENGINE")
    else:
        monkeypatch.setenv("FLUBNF_ENGINE", raw)
    world.act = ends
    sv = runner._supervisor()
    _job(world.alice)
    runner._dispatch(sv)
    # the install switched while the runner runs
    (install / ".flubnf.env").write_text("export FLUBNF_ENGINE=public\n",
                                         encoding="utf-8")
    _job(world.bob)
    runner._dispatch(sv)
    assert len(world.children) == 2
    for c in world.children:
        assert c.kw["env"]["FLUBNF_ENGINE"] == engine
        assert c.at_spawn["engine"] == engine
    assert runner.read_state()["engine"] == engine


# ------------------------------- a season whose build is unread (review #10)

SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"


def _fake_season(monkeypatch):
    """run_week writes a week's samples file; no filter runs."""
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def fake_week(root, _season, asof, *a, **k):
        wd = Path(root) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / retro.SAMPLES_JSON).write_text("{}")
    monkeypatch.setattr(retro, "run_week", fake_week)


def _builds(monkeypatch, build: dict) -> None:
    monkeypatch.setattr(EB, "engine_build", lambda path=None: dict(build))


def test_an_unread_build_is_recorded_as_its_engine():
    assert EB.engine_record(PUBLIC_UNREAD) == {"engine": "public"}
    assert EB.engine_record({}) == {"engine": "private"}
    assert EB.record(PUBLIC_UNREAD) == {}              # no commit to compare
    assert EB.engine_of({"engine": "public"}) == "public"
    # a resume on the other engine is a change, in words; on the same
    # engine it resumes, as a record from before builds were recorded does
    assert EB.change({"engine": "public"}, PRIVATE) == (
        "were fitted by the public engine (its build could not be read); "
        "this machine's engine is 2fdadee0 (feature/particle-filter)")
    assert EB.change({"engine": "private"}, PUBLIC_UNREAD) == (
        "were fitted by the private engine (its build could not be read); "
        "this machine's engine is the public one")
    assert EB.change({"engine": "public"}, PUBLIC) is None
    assert EB.change({"engine": "public"}, PUBLIC_UNREAD) is None
    assert EB.change({"engine": "private"}, PRIVATE) is None
    assert EB.change({}, PUBLIC) is None
    # the season rule reads it the same way, never as a record from
    # before builds were recorded
    prior = {"engine_build": {"engine": "public"}}
    assert retro.engine_build_change(prior, "pf", PUBLIC) is None
    assert "by the private engine" not in retro.engine_build_change(
        prior, "pf", PRIVATE)
    assert retro.engine_build_change(prior, "analogue", PRIVATE) is None


def test_a_public_season_whose_build_is_unread_keeps_its_engine(
        tmp_path, monkeypatch):
    _fake_season(monkeypatch)
    monkeypatch.setattr(fs, "_windows", lambda: False)
    _builds(monkeypatch, PUBLIC_UNREAD)
    root = tmp_path / SEASON

    def stop_after_first(asof):
        retro.stop_path(root).touch()
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1,
                         progress=stop_after_first)
    st = retro.read_meta(root)["settings"]
    assert st["engine_build"] == {"engine": "public"}
    # the copy switched to the private engine: refused (W5), naming the
    # engine the season began on and the step back to it
    _builds(monkeypatch, PRIVATE)
    with pytest.raises(retro.EngineBuildMismatch) as e:
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert str(e.value) == (
        f"{SEASON} at {root} has completed weeks that were fitted by the "
        "public engine (its build could not be read); this machine's engine "
        "is 2fdadee0 (feature/particle-filter). Resuming would mix two "
        "engine builds in one season. To finish it on the public engine it "
        "began on: ./setup_engine.sh --public in the FluBNF folder; or "
        "archive or discard the existing results to replay it on this one.")
    # back on the public engine, its build read now: it resumes, and the
    # record still names the engine alone (its first week's build unread)
    _builds(monkeypatch, PUBLIC)
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    meta = retro.read_meta(root)
    assert meta["status"] == "done" and retro.week_done(root, W2)
    assert meta["settings"]["engine_build"] == {"engine": "public"}


def test_a_groundhog_only_replay_records_no_engine_build(tmp_path,
                                                         monkeypatch):
    _fake_season(monkeypatch)
    _builds(monkeypatch, PUBLIC_UNREAD)
    root = tmp_path / SEASON
    retro.run_season(root, SEASON, ["Ohio"], width=1, engine="analogue")
    assert "engine_build" not in retro.read_meta(root)["settings"]


# --------------------------------------- the private remedy on a Mac

def test_the_mac_remedy_offers_the_double_click_only_where_the_copy_records_private(
        tmp_path, monkeypatch):
    """SetupEngine.command, double-clicked, follows the copy's record: a
    copy whose private choice came from the environment (the suite's pin)
    or from nothing would get the public engine from it.
    ./setup_engine.sh --private is right in every case."""
    monkeypatch.setattr(fs, "_windows", lambda: False)
    monkeypatch.setattr(fs, "INSTALL_ROOT", tmp_path)
    script = "run ./setup_engine.sh --private in the FluBNF folder"
    assert os.environ["FLUBNF_ENGINE"] == "private"          # the pin
    assert EB.setup_step("darwin") == script
    assert EB.archive_step("darwin") == (
        "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder and "
        + script)
    env = tmp_path / ".flubnf.env"
    env.write_text("export FLUBNF_ENGINE=public\n", encoding="utf-8")
    assert EB.setup_step("darwin") == script
    env.write_text('export FLUBNF_ENGINE="private"\n', encoding="utf-8")
    assert EB.setup_step("darwin") == (
        "double-click SetupEngine.command in the FluBNF folder (or run "
        "./setup_engine.sh --private there)")
    # the other platforms never depend on the record
    assert EB.setup_step("linux") == script
    assert EB.setup_step("win32") == "open FluBNF.bat again"


# ------------------------------------ a student's experiment (W5's remedy)

@pytest.mark.parametrize("began, now, engine, step", [
    (PRIVATE, PUBLIC, "private", "./setup_engine.sh --private"),
    # begun on the public engine with its build unread (review #10)
    (PUBLIC_UNREAD, PRIVATE, "public", "./setup_engine.sh --public")])
def test_an_experiment_begun_on_the_other_engine_is_told_to_delete_it(
        season, monkeypatch, began, now, engine, step):  # noqa: F811
    """A student's experiment has no archive: W5 there names deleting the
    experiment, as its other refusals do, never "archive or discard"."""
    s = {"model": "sihrs", "season": "2024-25"}
    _builds(monkeypatch, began)
    _weeks_run(monkeypatch, lambda root, asof: retro.request_stop(root))
    with pytest.raises(retro.SeasonStopped):
        X.replay(s, retro_root=season)
    _builds(monkeypatch, now)
    monkeypatch.setattr(fs, "_windows", lambda: False)
    said = _refused("MACHINE", X.preflight, s, retro_root=season)
    assert said.endswith(
        "Resuming would mix two engine builds in one season. To finish it "
        f"on the {engine} engine it began on: {step} in the FluBNF folder; "
        "or delete the experiment to replay it on this one."), said
    assert "archive" not in said


# ----------------------------------------------- the Sandbox's comparison

def test_a_comparison_names_the_two_engines(monkeypatch):
    """Two runs on different engines: the engine is the first setting the
    comparison lists. A run that records none ran on the private engine."""
    metas = {"a": {"seed": 1}, "b": {"engine": "public", "seed": 1},
             "c": {"engine": "private", "seed": 1}}
    monkeypatch.setattr(SE, "_run_meta", lambda r: (None, metas[r]))
    monkeypatch.setattr(SE, "run_files", lambda r: dict.fromkeys(
        ("model.bngl", "data.exp", "priors.conf"), ""))
    assert SE.RUN_SETTINGS[0] == "engine"
    assert SE.diff_runs("a", "b")["settings"] == [
        {"key": "engine", "label": "engine", "a": "private", "b": "public"}]
    assert SE.diff_runs("a", "c")["settings"] == []
    metas["c"]["seed"] = 2
    assert SE.diff_runs("b", "c")["settings"] == [
        {"key": "engine", "label": "engine", "a": "public", "b": "private"},
        {"key": "seed", "label": "seed", "a": 1, "b": 2}]


def test_the_data_tip_holds_on_either_engine(sandbox_root):
    from app.core import sandbox as sb
    sb.add_example("sir_example")
    html = client.get("/sandbox?model=sir_example").text
    tip = html.split('id="tt-sb-files"', 1)[1].split("</span></span>", 1)[0]
    line = tip.split("<b>data.exp:</b>", 1)[1].split("</span>", 1)[0]
    assert "-1" not in line
    assert ("On either engine the model starts a week before a first row at "
            "<code>t&nbsp;=&nbsp;0</code>; a missing week is a gap in "
            "time.") in line
    assert ("Keep a clock the model reads in a counter species, as "
            "FluBNF's own models do: <code>time()</code> runs on the "
            "private engine only.") in line
    for word in ("posterior", "adapt", "track", "follow"):
        assert word not in line, word


# ------------------------------------------ a research run's two-strain row

def test_a_skipped_two_strain_member_is_shown_beside_the_filter():
    spec = {"forecast_date": "2025-01-04", "extra": {"members": 3}}
    why = ("the two-strain member runs on the private engine only "
           "(FLUBNF_ENGINE=private)")
    html = runs.results_html({"pf_cells": 2, "pf2s_skipped": why}, spec)
    assert ('<tr><th scope="row">Two-strain fits</th><td>none: ' + why
            + "</td></tr>") in html
    assert html.index("Oracle SIHRS fits") < html.index("Two-strain fits")
    # beside "no engine" too, and its reason escaped
    html = runs.results_html({"pf_skipped": "engine venv not installed",
                              "pf2s_skipped": "a <b> reason"}, spec)
    assert "none: a &lt;b&gt; reason" in html
    assert "Two-strain fits" not in runs.results_html({"pf_cells": 2}, spec)


# ----------------------------------------------- the Windows record's @

@pytest.mark.parametrize("line, raw", [
    ('@set "FLUBNF_ENGINE=private"', "private"),
    ("@ set FLUBNF_ENGINE=private", "private"),
    ('@SET "flubnf_engine=Private"', "Private"),
    ('set "FLUBNF_ENGINE=private"', "private"),
    ('rem set "FLUBNF_ENGINE=private"', None),
    ('echo set "FLUBNF_ENGINE=private"', None)])
def test_the_windows_record_is_read_after_a_silencing_at(tmp_path, monkeypatch,
                                                          line, raw):
    """cmd sets a variable from `@set` as from `set`, so FluBNF.bat and the
    console read the same engine from such a line."""
    monkeypatch.setattr(fs, "_windows", lambda: True)
    (tmp_path / ".flubnf.env.cmd").write_bytes(
        b"@echo off\r\n" + line.encode() + b"\r\n")
    assert fs.recorded_engine_raw(tmp_path) == raw
    assert fs.recorded_engine(tmp_path) == (None if raw is None
                                            else fs.engine_name(raw))
