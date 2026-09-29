"""The particle-filter engine's build (branch, commit, local edits): read
from git or an archive's VERSION stamp, compared with production, shown on
Home, Forecast and doctor, recorded on every run and retrospective week, and
a season is never resumed on another build. No engine is installed here:
flubnf.settings.PYBNF points at temporary folders."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import flubnf.settings as fs
from app.core import engine_build as EB
from app.core import retro
from app.core.runs import Ledger, RunSpec, version_pairs
from app.ui import server as srv
from app.ui import versions as V

client = TestClient(srv.app)

PROD = {"branch": EB.PRODUCTION_ENGINE_BRANCH, "commit": "2fdadee0",
        "dirty": False, "source": "git", "path": "/x/PyBNF-pf"}
OTHER = {"branch": "feature/bngsim", "commit": "4bbc4672", "dirty": True,
         "source": "git", "path": "/x/PyBNF-pf"}


@pytest.fixture(autouse=True)
def _isolated():
    """The cached build, the flash/status and the retro claims are module
    state: restored after each test."""
    from app.ui import retro_seasons as RS
    from app.ui import shared
    from app.ui import state as S
    saved = dict(V.ENGINE_BUILD)
    status = dict(S._status)
    claims = (dict(RS._retro_status), dict(RS._retro_claim_at))
    yield
    V.ENGINE_BUILD.clear()
    V.ENGINE_BUILD.update(saved)
    S._status.clear()
    S._status.update(status)
    for d, before in zip((RS._retro_status, RS._retro_claim_at), claims):
        d.clear()
        d.update(before)
    shared._invalidate_scans()


def _git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "-c", "user.name=t",
                        "-c", "user.email=t@t", *args],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A real git checkout on feature/particle-filter with one commit."""
    r = tmp_path / "PyBNF-pf"
    (r / "pybnf").mkdir(parents=True)
    (r / "pybnf" / "parse.py").write_text("x = 1\n")
    _git(r, "init", "-q", "-b", "feature/particle-filter")
    _git(r, "add", ".")
    _git(r, "commit", "-q", "-m", "engine")
    return r


# --------------------------------------------------------------- engine_build
def test_a_clean_checkout_names_its_branch_and_commit(repo):
    b = EB.engine_build(repo)
    sha = _git(repo, "rev-parse", "HEAD")
    assert b == {"branch": "feature/particle-filter", "commit": sha[:8],
                 "dirty": False, "source": "git", "path": str(repo)}


def test_an_edited_tracked_file_is_dirty_and_untracked_files_are_not(repo):
    (repo / "notes.txt").write_text("scratch\n")        # untracked: ignored
    assert EB.engine_build(repo)["dirty"] is False
    (repo / "pybnf" / "parse.py").write_text("x = 2\n")
    assert EB.engine_build(repo)["dirty"] is True


def test_a_detached_head_has_no_branch(repo):
    sha = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "--detach", sha)
    b = EB.engine_build(repo)
    assert b["branch"] == "" and b["commit"] == sha[:8]
    assert b["source"] == "git"
    assert EB.label(b) == sha[:8]


def test_a_folder_that_is_not_a_repo_is_unknown(tmp_path):
    d = tmp_path / "plain"
    (d / "pybnf").mkdir(parents=True)
    b = EB.engine_build(d)
    assert b["source"] == "unknown" and b["commit"] == ""
    assert not EB.known(b) and not EB.is_production(b)


def test_an_archive_install_reads_its_version_stamp(tmp_path):
    d = tmp_path / "PyBNF-Private"
    (d / "pybnf").mkdir(parents=True)
    (d / "VERSION").write_text("feature/particle-filter 2fdadee0\n"
                               "cut 2026-09-01 from git@example:fork.git\n"
                               "subject: engine\n")
    b = EB.engine_build(d)
    assert b == {"branch": "feature/particle-filter", "commit": "2fdadee0",
                 "dirty": False, "source": "archive", "path": str(d)}
    assert EB.is_production(b)
    assert EB.archive_step() in EB.fix(dict(b, commit="1234abcd"))


def test_a_missing_folder_is_unknown_and_never_raises(tmp_path):
    b = EB.engine_build(tmp_path / "nowhere")
    assert b["source"] == "unknown" and not EB.known(b)
    assert EB.engine_build("")["source"] == "unknown"


def test_the_default_path_is_settings_pybnf(repo, monkeypatch):
    monkeypatch.setattr(fs, "PYBNF", repo)
    assert EB.engine_build()["path"] == str(repo)


# -------------------------------------------------------------- is_production
@pytest.mark.parametrize("build, want", [
    (PROD, True),
    (dict(PROD, branch="feature/bngsim"), True),          # branch informative
    (dict(PROD, branch=""), True),                        # detached HEAD
    (dict(PROD, commit="2fdadee0a1b2c3d4"), True),        # longer sha
    (dict(PROD, source="archive"), True),
    (dict(PROD, dirty=True), False),                      # local edits
    (OTHER, False),
    (dict(OTHER, dirty=False), False),
    (dict(PROD, commit="2fdade"), False),                 # too short to say
    ({}, False), (None, False),
])
def test_is_production(build, want):
    assert EB.is_production(build) is want


def test_the_warning_names_the_build_and_the_fix_names_the_path():
    assert EB.warning(PROD) == "" and EB.warning({}) == ""
    assert EB.warning(OTHER) == (
        "The engine is feature/bngsim at 4bbc4672, not the production build "
        "2fdadee0 on feature/particle-filter, and has local changes.")
    fix = EB.fix(OTHER, platform="darwin")
    assert fix == ("FluBNF moves a clean checkout on feature/particle-filter "
                   "to the production build each time it opens. To switch, "
                   "stash the local edits first (git stash in that folder), "
                   'then run git -C "/x/PyBNF-pf" checkout '
                   "feature/particle-filter and reopen FluBNF. Without access "
                   "to the private fork (a checkout cloned from a bundle), "
                   "rename the engine folder so FluBNF stops using it, then "
                   "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder "
                   "and double-click SetupEngine.command in the FluBNF folder "
                   "(or run ./setup_engine.sh there). Research runs may use "
                   "other builds on purpose.")
    assert "stash" not in EB.fix(dict(OTHER, dirty=False))


# ------------------------------------------------------------- the fix text
def test_the_archive_step_names_this_machines_installer():
    assert EB.archive_step("win32") == (
        "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder and open "
        "FluBNF.bat again")
    assert EB.archive_step("darwin") == (
        "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder and "
        "double-click SetupEngine.command in the FluBNF folder (or run "
        "./setup_engine.sh there)")
    assert EB.archive_step("linux") == (
        "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder and run "
        "./setup_engine.sh in the FluBNF folder")


@pytest.mark.parametrize("build", [
    dict(OTHER, source="archive", path="C:\\Users\\Ely Miller\\AppData\\Local"
         "\\FluBNF\\PyBNF-Private"),
    dict(OTHER, path="C:\\Users\\Ely Miller\\Documents\\GitHub\\PyBNF-pf"),
    dict(OTHER, dirty=False, branch=EB.PRODUCTION_ENGINE_BRANCH),
])
def test_no_windows_fix_names_a_script_windows_cannot_run(build):
    text = EB.fix(build, platform="win32")
    for gone in ("setup_engine.sh", "SetupEngine.command", "git pull"):
        assert gone not in text, (gone, text)
    assert "open FluBNF.bat again" in text


def test_the_git_fix_quotes_the_path_and_offers_the_archive_to_a_bundle_clone():
    path = "C:\\Users\\Ely Miller\\Documents\\GitHub\\PyBNF-pf"
    text = EB.fix(dict(OTHER, path=path, dirty=False), platform="win32")
    # the command pastes whole: quoted path, nothing stuck to the branch
    assert (f'run git -C "{path}" checkout feature/particle-filter and '
            "reopen FluBNF.") in text
    # the launcher's update then moves it; no pull that overshoots the
    # pinned commit or needs the access a bundle clone lacks
    assert "git pull" not in text
    assert ("Without access to the private fork (a checkout cloned from a "
            "bundle), rename the engine folder so FluBNF stops using it, then "
            "save pybnf-pf-2fdadee0.tar.gz in your Downloads folder and open "
            "FluBNF.bat again.") in text
    assert text.endswith("Research runs may use other builds on purpose.")


def test_an_archive_install_is_replaced_by_the_newer_archive():
    arch = dict(PROD, source="archive", commit="1234abcd")
    assert EB.fix(arch, platform="win32") == (
        "This engine was installed from an archive. To replace it, save "
        "pybnf-pf-2fdadee0.tar.gz in your Downloads folder and open "
        "FluBNF.bat again.")


# -------------------------------------------- a checkout git cannot read
def _git_says(monkeypatch, rc: int, err: str):
    """Every git call fails as git would with `err` on stderr."""
    monkeypatch.setattr(EB, "_git", lambda path, *a, **k: (rc, "", err))


DUBIOUS = ("fatal: detected dubious ownership in repository at "
           "'C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf'\n"
           "'C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf' is owned by:\n"
           "\tBUILTIN/Administrators (S-1-5-32-544)\n"
           "but the current user is:\n"
           "\tLAB/ely (S-1-5-21-1-2-3-1001)\n"
           "To add an exception for this directory, call:\n\n"
           "\tgit config --global --add safe.directory "
           "'C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf'\n")


def test_a_checkout_another_account_owns_is_unreadable_not_unknown(
        tmp_path, monkeypatch):
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)
    # a VERSION stamp would be a guess: a checkout does not carry one
    (d / "VERSION").write_text("feature/particle-filter 2fdadee0\n")
    _git_says(monkeypatch, 128, DUBIOUS)
    b = EB.engine_build(d)
    assert b["source"] == "unreadable" and b["commit"] == ""
    assert b["error"] == ("fatal: detected dubious ownership in repository "
                          "at 'C:/Users/Ely Miller/AppData/Local/FluBNF/"
                          "PyBNF-pf'")
    assert not EB.is_production(b) and EB.record(b) == {}
    assert EB.warning(b) == (
        f"git could not read {d}: detected dubious ownership in repository "
        "at 'C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf'.")
    # git's own command, the path as git spells it; on Windows in double
    # quotes, which cmd.exe and PowerShell both read
    win = EB.fix(b, platform="win32")
    assert ("run git config --global --add safe.directory "
            '"C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf" and reopen '
            "FluBNF.") in win
    assert ("git config --global --add safe.directory "
            "'C:/Users/Ely Miller/AppData/Local/FluBNF/PyBNF-pf'") \
        in EB.fix(b, platform="darwin")


def test_a_machine_without_git_is_told_to_install_it(tmp_path, monkeypatch):
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)

    def no_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(EB.subprocess, "run", no_git)
    b = EB.engine_build(d)
    assert b["source"] == "unreadable"
    assert b["error"] == "git is not installed or not on PATH"
    assert EB.warning(b) == (f"git could not read {d}: git is not installed "
                             "or not on PATH.")
    assert EB.fix(b, platform="win32") == (
        "Install Git for Windows (https://git-scm.com/download/win), then "
        "open FluBNF.bat again.")
    assert "xcode-select" in EB.fix(b, platform="darwin")


def test_a_folder_git_does_not_recognise_names_git_and_the_archive(tmp_path):
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)                   # not a repository
    b = EB.engine_build(d)
    assert b["source"] == "unreadable"
    assert b["error"].startswith("fatal: not a git repository")
    text = EB.fix(b, platform="win32")
    assert text.startswith(f'Run git -C "{d}" status to see why.')
    assert EB.archive_step("win32") in text


def test_the_unreadable_checkout_shows_on_home_and_in_doctor(
        tmp_path, monkeypatch):
    from flubnf import doctor
    d = tmp_path / "PyBNF-pf"
    (d / ".git").mkdir(parents=True)
    _git_says(monkeypatch, 128, DUBIOUS)
    html = _home_with(monkeypatch, d)
    assert 'data-engine-build="unreadable"' in html
    assert f"git could not read {d}: detected dubious ownership" in html
    assert "safe.directory" in html
    assert 'data-engine-build="unreadable"' in client.get("/forecast").text
    assert "engine build unknown" in client.get("/forecast").text
    # doctor: a WARN with git's reason, never "has no .git"
    c = doctor._check_engine_build()
    assert c.status is doctor.Status.WARN
    assert c.detail.startswith(f"git could not read {d}: ")
    assert "has no .git" not in c.detail and "safe.directory" in c.hint


def test_a_slow_status_is_asked_again_before_it_counts_as_edited(
        repo, monkeypatch):
    real = EB._git
    seen = []

    def slow_once(path, *args, timeout=EB.GIT_TIMEOUT_S):
        if args[0] == "status":
            seen.append(timeout)
            if len(seen) == 1:
                return -1, "", "git did not answer within 10 s"
        return real(path, *args, timeout=timeout)
    monkeypatch.setattr(EB, "_git", slow_once)
    b = EB.engine_build(repo)
    assert b["dirty"] is False and b["source"] == "git"
    # status has its own, longer limit than the other calls
    assert seen == [EB.STATUS_TIMEOUT_S, EB.STATUS_TIMEOUT_S]
    assert EB.STATUS_TIMEOUT_S >= 10 > EB.GIT_TIMEOUT_S
    # twice without an answer: never "production" on a check that did not run
    seen.clear()

    def never(path, *args, timeout=EB.GIT_TIMEOUT_S):
        if args[0] == "status":
            seen.append(timeout)
            return -1, "", "git did not answer within 10 s"
        return real(path, *args, timeout=timeout)
    monkeypatch.setattr(EB, "_git", never)
    assert EB.engine_build(repo)["dirty"] is True
    assert len(seen) == 2


# ---------------------------------------------------------------------- Home
def _home_with(monkeypatch, path) -> str:
    monkeypatch.setattr(fs, "PYBNF", path)
    V.refresh_engine_build()
    return client.get("/").text


def test_home_names_the_production_build_without_a_warning(tmp_path,
                                                          monkeypatch):
    d = tmp_path / "PyBNF-pf"
    d.mkdir()
    (d / "VERSION").write_text("feature/particle-filter 2fdadee0\n")
    html = _home_with(monkeypatch, d)
    # the Setup card's PyBNF value is the build
    label = "<span data-engine-label>2fdadee0 (feature/particle-filter)</span>"
    assert label in html
    assert html.rfind("<dt>PyBNF</dt>", 0, html.index(label)) != -1
    assert 'data-engine-build="other"' not in html


def test_home_warns_on_another_build(repo, monkeypatch):
    (repo / "pybnf" / "parse.py").write_text("x = 2\n")
    html = _home_with(monkeypatch, repo)
    sha = _git(repo, "rev-parse", "HEAD")[:8]
    assert 'data-engine-build="other"' in html
    assert (f"The engine is feature/particle-filter at {sha}, not the "
            "production build 2fdadee0 on feature/particle-filter, and has "
            "local changes.") in html
    # the path quoted (a Windows profile folder can hold a space), escaped
    assert f"git -C &#34;{repo}&#34; checkout feature/particle-filter" in html
    # the forecast tab's engine row says it too, in one line
    assert 'data-engine-build="other"' in client.get("/forecast").text


def test_home_without_an_engine_shows_no_build(tmp_path, monkeypatch):
    html = _home_with(monkeypatch, tmp_path / "nowhere")
    assert 'data-engine-build' not in html
    assert 'data-vkey="pybnf"' in html


# -------------------------------------------------------------------- doctor
def test_doctor_names_the_build_and_warns_off_production(repo, monkeypatch):
    from flubnf import doctor
    monkeypatch.setattr(fs, "PYBNF", repo)
    c = doctor._check_engine_build()
    sha = _git(repo, "rev-parse", "HEAD")[:8]
    assert c.status is doctor.Status.WARN
    assert f"feature/particle-filter at {sha}" in c.detail
    assert "not the production build 2fdadee0" in c.detail
    assert f'git -C "{repo}" checkout feature/particle-filter' in c.hint
    assert "PyBNF engine build" in {x.name for x in doctor.run_doctor().checks}


def test_doctor_passes_the_production_build(tmp_path, monkeypatch):
    from flubnf import doctor
    d = tmp_path / "PyBNF-Private"
    d.mkdir()
    (d / "VERSION").write_text("feature/particle-filter 2fdadee0\n")
    monkeypatch.setattr(fs, "PYBNF", d)
    c = doctor._check_engine_build()
    assert c.status is doctor.Status.OK
    assert "2fdadee0 (feature/particle-filter), the production build" in c.detail


def test_doctor_cli_prints_the_warning_and_does_not_fail_on_it(repo,
                                                               monkeypatch):
    from typer.testing import CliRunner
    from flubnf import doctor
    from flubnf.cli import app
    monkeypatch.setattr(fs, "PYBNF", repo)
    only = doctor._check_engine_build
    monkeypatch.setattr(doctor, "run_doctor", lambda **k: doctor.DoctorReport(
        checks=[only()]))
    r = CliRunner().invoke(app, ["doctor"], env={"COLUMNS": "400"})
    assert r.exit_code == 0, r.output
    assert "not the production build" in r.output
    assert "checkout feature/particle-filter" in r.output


# -------------------------------------------------------------------- ledger
def test_the_ledger_records_the_build_and_the_run_page_shows_it(
        repo, monkeypatch):
    monkeypatch.setattr(fs, "PYBNF", repo)
    ev = V._engine_versions_for_ledger("pf,analogue")
    sha = _git(repo, "rev-parse", "HEAD")[:8]
    assert ev["engines"] == "pf,analogue"
    assert ev["pybnf_build"] == {"branch": "feature/particle-filter",
                                 "commit": sha, "dirty": False,
                                 "source": "git"}
    assert "path" not in ev["pybnf_build"]
    rid = Ledger().open_run(RunSpec(engine="all", forecast_date="2098-01-03"),
                            Path("pending"), ev)
    row = Ledger().row(rid)
    assert json.loads(row["engine_versions"])["pybnf_build"]["commit"] == sha
    # the run page and the weekly report both read the row
    from app.ui import pipeline
    want = ("PyBNF build",
            f"{sha} (feature/particle-filter), not the production build")
    assert want in pipeline._build_pairs(row)
    page = client.get(f"/runs/{rid}").text
    assert f"<dt>PyBNF build</dt><dd>{sha} (feature/particle-filter), " \
           "not the production build</dd>" in page


def test_no_engine_records_no_build_and_older_rows_show_none(tmp_path,
                                                             monkeypatch):
    monkeypatch.setattr(fs, "PYBNF", tmp_path / "nowhere")
    assert "pybnf_build" not in V._engine_versions_for_ledger("pf,analogue")
    assert not [p for p in version_pairs("abc", {"pybnf": "1.2"})
                if p[0] == "PyBNF build"]
    assert ("PyBNF build", "2fdadee0 (feature/particle-filter)") in \
        version_pairs("", {"pybnf_build": EB.record(PROD)})


# ------------------------------------------------------------- retrospective
SEASON, W1, W2 = "2098-99", "2098-11-07", "2098-11-14"


def _fake_pf_season(monkeypatch):
    """run_week writes a week's samples file; no filter runs."""
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])

    def fake_week(root, season, asof, *a, **k):
        wd = Path(root) / "weeks" / asof
        wd.mkdir(parents=True, exist_ok=True)
        (wd / retro.SAMPLES_JSON).write_text("{}")
    monkeypatch.setattr(retro, "run_week", fake_week)


def test_a_season_records_each_weeks_build_and_refuses_another(
        repo, tmp_path, monkeypatch):
    _fake_pf_season(monkeypatch)
    monkeypatch.setattr(fs, "PYBNF", repo)
    sha = _git(repo, "rev-parse", "HEAD")[:8]
    root = tmp_path / SEASON
    stop_after = {"n": 0}

    def one_week(asof):
        stop_after["n"] += 1
        if stop_after["n"] == 1:
            retro.stop_path(root).touch()
    with pytest.raises(retro.SeasonStopped):
        retro.run_season(root, SEASON, ["Ohio"], width=1, progress=one_week)
    meta = retro.read_meta(root)
    rec = {"branch": "feature/particle-filter", "commit": sha,
           "dirty": False, "source": "git"}
    assert meta["settings"]["engine_build"] == rec
    assert meta["week_engine_builds"] == {W1: rec}
    assert ("PyBNF build",
            f"{sha} (feature/particle-filter), not the production build") \
        in retro.settings_summary(meta)
    # local edits since: refused in plain words, nothing recorded
    (repo / "pybnf" / "parse.py").write_text("x = 2\n")
    with pytest.raises(retro.EngineBuildMismatch,
                       match="mix two engine builds"):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert retro.read_meta(root)["week_engine_builds"] == {W1: rec}
    # the same build again resumes and records the second week
    _git(repo, "checkout", "--", "pybnf/parse.py")
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    assert retro.read_meta(root)["week_engine_builds"] == {W1: rec, W2: rec}


def test_an_engine_changed_mid_season_stops_it_before_the_next_week(
        repo, tmp_path, monkeypatch):
    """The build is re-read before every filter week: an edit (or a branch
    switch) during an overnight replay stops the season before a week is
    fitted by another engine, says why, and resumes once switched back."""
    _fake_pf_season(monkeypatch)
    monkeypatch.setattr(fs, "PYBNF", repo)
    root = tmp_path / SEASON

    def edit_after_first(asof):
        if asof == W1:
            (repo / "pybnf" / "parse.py").write_text("x = 2\n")
    with pytest.raises(retro.EngineBuildChanged,
                       match="engine changed during the replay"):
        retro.run_season(root, SEASON, ["Ohio"], width=1,
                         progress=edit_after_first)
    meta = retro.read_meta(root)
    assert meta["status"] == "stopped"
    assert f"stopped before {W2}" in meta["stop_reason"]
    assert retro.week_done(root, W1) and not retro.week_done(root, W2)
    assert list(meta["week_engine_builds"]) == [W1]
    # a resume on the edited engine is refused (the completed week's build)
    with pytest.raises(retro.EngineBuildMismatch):
        retro.run_season(root, SEASON, ["Ohio"], width=1)
    # switched back: resumes, fits the second week, and clears the reason
    _git(repo, "checkout", "--", "pybnf/parse.py")
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    meta = retro.read_meta(root)
    assert retro.week_done(root, W2) and "stop_reason" not in meta
    assert meta["status"] == "done"


def test_a_season_with_no_recorded_build_resumes_as_before(
        repo, tmp_path, monkeypatch):
    _fake_pf_season(monkeypatch)
    monkeypatch.setattr(fs, "PYBNF", repo)
    root = tmp_path / SEASON
    (root / "weeks" / W1).mkdir(parents=True)
    (root / "weeks" / W1 / retro.SAMPLES_JSON).write_text("{}")
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "locations": ["Ohio"]}})
    retro.run_season(root, SEASON, ["Ohio"], width=1)
    meta = retro.read_meta(root)
    assert "engine_build" not in meta["settings"]    # never stamped
    assert list(meta["week_engine_builds"]) == [W2]  # the week it did fit
    assert retro.engine_build_change(meta["settings"]) is None


def test_the_engine_build_rule_skips_groundhog_only_replays():
    prior = {"engine_build": EB.record(PROD)}
    assert retro.engine_build_change(prior, "analogue", OTHER) is None
    assert retro.engine_build_change(prior, "pf", PROD) is None
    msg = retro.engine_build_change(prior, "pf", OTHER)
    assert msg == ("were fitted by engine 2fdadee0 (feature/particle-filter); "
                   "this machine's engine is 4bbc4672 (feature/bngsim, local "
                   "changes)")
    assert "not found" in retro.engine_build_change(prior, "pf", {})


def test_the_retro_route_refuses_a_resume_on_another_build(tmp_path,
                                                            monkeypatch):
    from app.ui import retro_seasons as RS
    from app.ui import state as S
    from app.ui.routes import retro as ui_retro
    monkeypatch.setattr(RS, "RETRO_ROOT", tmp_path)
    monkeypatch.setattr(RS, "RETRO_SEAL", tmp_path / "noseal")
    monkeypatch.setattr(retro, "available_seasons", lambda: [SEASON])
    monkeypatch.setattr(retro, "season_vintages", lambda s: [W1, W2])
    launched = []
    monkeypatch.setattr(ui_retro, "_retro_bg",
                        lambda *a, **k: launched.append(a))
    root = tmp_path / SEASON
    (root / "weeks" / W1).mkdir(parents=True)
    six = ["Alaska", "New York", "Wyoming", "Pennsylvania", "Vermont",
           "California"]
    retro.write_meta(root, {"season": SEASON, "status": "stopped",
                            "settings": {"season": SEASON, "engine": "pf",
                                         "scope": "panel6", "locations": six,
                                         "engine_build": EB.record(PROD)}})
    monkeypatch.setattr(RS, "_weeks_done", lambda p: 1)
    monkeypatch.setattr(EB, "engine_build", lambda path=None: dict(OTHER))
    form = {"season": SEASON, "engine": "pf", "mode": "resume",
            "locations": "panel6", "national": "0"}
    RS._retro_status.pop(SEASON, None)
    client.post("/retro/run", data=form, follow_redirects=False)
    assert launched == []
    flash = S._status.get("flash", "")
    assert "mix two engine builds" in S._status.get("flash_detail", "")
    assert flash.startswith("Not started") and S._status["flash_kind"] == "warn"
    assert "4bbc4672 (feature/bngsim, local changes)" in flash
    # the recorded build resumes
    monkeypatch.setattr(EB, "engine_build", lambda path=None: dict(PROD))
    RS._retro_status.pop(SEASON, None)
    client.post("/retro/run", data=form, follow_redirects=False)
    assert len(launched) == 1
