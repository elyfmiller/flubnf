"""The cutover's parts that read the engine this copy runs, on the public
engine, the default, beside the private engine, the fallback: the ledger's
engine build, the version snapshot a launch reuses, the pages' words for a
missing engine, and the Setup card's line naming the engine. The settings
rule itself (engine_choice and the install's record) is test_engine_lwf's.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from app.core import engine_build as EB
from app.core.engines import lwf
from app.core.runs import Ledger, RunSpec
from app.ui import pipeline as ui_pipeline
from app.ui import versions as V
from flubnf import settings


@pytest.fixture
def private_installed(tmp_path, monkeypatch):
    """The private engine, the fallback, installed here (its two files)."""
    py = tmp_path / "engine" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    fork = tmp_path / "PyBNF-pf"
    (fork / "pybnf").mkdir(parents=True)
    (fork / "pybnf" / "pf.py").write_text("")
    monkeypatch.setattr(settings, "PY_ENGINE", py)
    monkeypatch.setattr(settings, "PYBNF", fork)
    return fork


# --- the ledger -----------------------------------------------------------------

def _pybnf_sha(path) -> str:
    db = sqlite3.connect(path)
    try:
        return db.execute("SELECT pybnf_sha FROM runs").fetchone()[0]
    finally:
        db.close()


def test_the_ledger_names_the_public_build_on_the_public_engine(
        tmp_path, monkeypatch):
    """Under public a row names the public engine's commit, never the
    private checkout's SHA (2fdadee0 on the first public round)."""
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setattr(lwf, "public_build",
                        lambda: {"engine": "public", "commit": "8410f794"})
    led = Ledger(tmp_path / "ledger.sqlite")
    led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"), tmp_path,
                 {})
    assert _pybnf_sha(tmp_path / "ledger.sqlite") == "8410f794"
    # a venv that names no commit
    monkeypatch.setattr(lwf, "public_build", lambda: {"commit": ""})
    led2 = Ledger(tmp_path / "ledger2.sqlite")
    led2.open_run(RunSpec(engine="all", forecast_date="2098-01-03"), tmp_path,
                  {})
    assert _pybnf_sha(tmp_path / "ledger2.sqlite") == "unknown"


def test_the_ledger_names_the_fork_on_the_private_engine(tmp_path,
                                                         monkeypatch):
    from app.core import runs
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    monkeypatch.setattr(lwf, "public_build", lambda: (_ for _ in ()).throw(
        AssertionError("the public build was read on the private engine")))
    monkeypatch.setattr(runs, "_git_sha", lambda path: "2fdadee0aaaa")
    led = Ledger(tmp_path / "ledger.sqlite")
    led.open_run(RunSpec(engine="all", forecast_date="2098-01-03"), tmp_path,
                 {})
    assert _pybnf_sha(tmp_path / "ledger.sqlite") == "2fdadee0aaaa"


# --- the version snapshot -------------------------------------------------------

@pytest.mark.parametrize("snap, kept_on", [
    ({"engine": "public"}, "public"),
    ({"engine": "private"}, "private"),
    # from before the engine was stored: its build says, else private
    ({"engine_build": {"engine": "public", "commit": "8410f794"}}, "public"),
    ({"engine_build": {"branch": "feature/particle-filter",
                       "commit": "2fdadee0"}}, "private"),
    ({}, "private"),
])
def test_a_snapshot_made_under_the_other_engine_is_discarded(
        tmp_path, monkeypatch, snap, kept_on):
    path = tmp_path / "component_versions.json"
    path.write_text(json.dumps({**snap, "pybnf": "9.9.9"}), encoding="utf-8")
    monkeypatch.setattr(V, "_VERSIONS_SNAPSHOT", path)
    for engine in ("public", "private"):
        monkeypatch.setenv("FLUBNF_ENGINE", engine)
        initial = V._versions_initial()
        if engine == kept_on:
            assert initial["pybnf"] == "9.9.9", engine
        else:
            assert V._snapshot() == {}, engine
            assert initial["pybnf"] == V.VERSION_PENDING, engine


# --- the pages' words for a missing engine (W7) ----------------------------------

def test_a_missing_public_engine_names_its_step_and_the_fallback(
        private_installed, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setattr(settings, "_windows", lambda: False)
    monkeypatch.setattr(lwf.sys, "platform", "darwin")
    assert ui_pipeline._pf_engine_missing("ready") == ""
    assert ui_pipeline._pf_engine_missing("absent") == (
        "which is not installed yet on this machine (the public engine, the "
        "default since this update: to install it, run ./setup_engine.sh "
        "--public in the FluBNF folder (SetupEngine.command on a Mac does the "
        "same); the private engine installed here runs instead after "
        "./setup_engine.sh --private in the FluBNF folder)")
    # without the private engine: the install step alone
    monkeypatch.setattr(settings, "PYBNF", private_installed / "gone")
    assert ui_pipeline._pf_engine_missing("absent") == (
        "which is not installed on this machine (to install it, run "
        "./setup_engine.sh --public in the FluBNF folder (SetupEngine.command "
        "on a Mac does the same))")


def test_a_missing_private_engine_keeps_todays_words(private_installed,
                                                     monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "private")
    assert ui_pipeline._pf_engine_missing("absent") == (
        "which is not installed on this machine")
    assert ui_pipeline._pf_engine_missing("broken") == (
        "whose install is incomplete")


def test_the_windows_words_name_its_steps(private_installed, monkeypatch):
    monkeypatch.setenv("FLUBNF_ENGINE", "public")
    monkeypatch.setattr(settings, "_windows", lambda: True)
    monkeypatch.setattr(lwf.sys, "platform", "win32")
    said = ui_pipeline._pf_engine_missing("absent")
    assert "to install it, open FluBNF.bat again; it installs it;" in said
    assert said.endswith("runs instead after setup.ps1 -Engine private, then "
                         "open FluBNF.bat again)")


# --- the engine in words (Home's Setup card) -------------------------------------

def test_home_names_the_engine_this_copy_runs(monkeypatch):
    from fastapi.testclient import TestClient
    from app.ui import server as srv
    client = TestClient(srv.app)
    for engine in ("public", "private"):
        monkeypatch.setenv("FLUBNF_ENGINE", engine)
        html = client.get("/").text
        words = EB.engine_words(engine).replace("'", "&#39;")
        assert f"This copy runs {words}." in html, engine


def test_the_badge_names_the_engine_of_a_private_build():
    """W6: the ok badge says the engine beside the commit; a private build
    says so, a public one needs no word (the default)."""
    from app.ui.server import templates
    tpl = templates.env.get_template("_engine_build.html")
    for build, says in (
            ({"engine": "public", "commit": "8410f794"}, "PyBNF 8410f794"),
            ({"branch": "feature/particle-filter", "commit": "2fdadee0"},
             "PyBNF 2fdadee0, private engine")):
        view = {"label": "x", "warning": "", "fix": "", "production": True,
                "known": True, "commit": build["commit"],
                "engine": EB.engine_of(build)}
        html = " ".join(tpl.render(engine_build_view=lambda v=view: v,
                                   eb_ok=True).split())
        assert says in html, (build, html)
        if build.get("engine") == "public":
            assert "private engine" not in html
