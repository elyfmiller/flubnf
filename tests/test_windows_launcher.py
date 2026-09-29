"""FluBNF.bat, the Windows launcher: its self-update and engine-file blocks.

cmd.exe reads a batch file as it runs it. When the `git merge` on line 65
replaces FluBNF.bat, cmd carries on at the same byte offset in the new copy,
so the bytes an update resumes at are pinned here, on every platform. The
new blocks are checked as text everywhere; on Windows they are also sliced
out of FluBNF.bat and run with cmd.exe against real clones, as
tests/test_launcher_update.py runs FluBNF.command's.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
# The CRLF form users run (.gitattributes: *.bat eol=crlf), whatever line
# endings this checkout has.
BAT_BYTES = (REPO / "FluBNF.bat").read_bytes().replace(
    b"\r\n", b"\n").replace(b"\n", b"\r\n")
BAT = BAT_BYTES.decode("ascii")
LINES = BAT.split("\r\n")

# Where cmd resumes in a FluBNF.bat that git replaced mid-run: after line
# 65's merge (every copy since 2026-09-09), and after the stash-path merge on
# line 83 of the copies from then until this block was rewritten.
FROZEN_END = 3317
FROZEN_SHA256 = "f604a0b9bb1a00d41693bb6d1e7cec128d2a9c7124a9ad18120f3487afbbd653"
STASH_LANDING = 4049
# Labels a copy that ran before an update jumps to, in the copy git left.
KEPT_LABELS = ("deps", "uptodate", "updatedaround")

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="runs FluBNF.bat's blocks with cmd.exe")


def _line_at(offset: int) -> str:
    assert BAT_BYTES[offset - 2:offset] == b"\r\n", (
        f"byte {offset} of FluBNF.bat is in the middle of a line")
    return BAT_BYTES[offset:].split(b"\r\n", 1)[0].decode("ascii")


def _label_at(name: str) -> int:
    return LINES.index(f":{name}")


def _update_block() -> list[str]:
    """Lines from the one after the frozen merge to the :deps label."""
    first = BAT_BYTES[:FROZEN_END].count(b"\r\n")
    return LINES[first:_label_at("deps")]


def _engine_section() -> str:
    start = re.search(r"^:launch\r?$", BAT, re.MULTILINE)
    end = re.search(r"^:startconsole\r?$", BAT, re.MULTILINE)
    return BAT[start.start():end.start()]


def _after_label(text: str, name: str, until: str | None = None) -> str:
    """What follows the line `:name` (not a `goto :name`), up to `until`."""
    m = re.search(rf"^:{name}\r?$", text, re.MULTILINE)
    assert m, f"FluBNF.bat has no :{name} label"
    rest = text[m.end():]
    return rest if until is None else rest.split(until, 1)[0]


# ------------------------------------------------ the bytes an update resumes at
def test_the_lines_an_update_resumes_after_never_change():
    head = BAT_BYTES[:FROZEN_END]
    assert hashlib.sha256(head).hexdigest() == FROZEN_SHA256, (
        "FluBNF.bat's lines 1-65 changed. cmd.exe reads a batch file as it "
        "runs it, and the `git merge` on line 65 replaces this file mid-run: "
        "cmd then carries on at byte 3317 of the NEW copy, where the old "
        "copy's line 66 began. Any edit above that line makes the first open "
        "after an update start in the middle of a line (with --prune added "
        "to line 51 it runs `l 2>&1`, and a clean clone is told local edits "
        "block the update). Put new logic after line 65. If lines 1-65 truly "
        "must change, pad the new file so byte 3317 still starts a harmless "
        "line, check every older layout, and only then update this hash.")
    assert head.endswith(b"git merge --ff-only -q origin/%BRANCH% >nul 2>&1\r\n")
    first = _line_at(FROZEN_END)
    assert first.startswith(("if errorlevel 1", "if not errorlevel 1")), (
        "the line cmd resumes at after the line-65 merge must read that "
        f"merge's result first, and it is now: {first!r}")


def test_an_older_copy_setting_edits_aside_lands_on_a_jump():
    """Copies of FluBNF.bat from before this block was rewritten stash local
    edits and merge on their line 83; cmd then resumes at byte 4049 of the
    new copy. A goto there sends that run to the "set aside" message."""
    assert _line_at(STASH_LANDING) == "goto :updatedaround", (
        "byte 4049 of FluBNF.bat no longer starts `goto :updatedaround`: an "
        "older copy that set edits aside and merged resumes there. Lengthen "
        "or shorten the padding comment just above it.")
    before = [ln for ln in BAT_BYTES[:STASH_LANDING].decode("ascii")
              .split("\r\n")[:-1] if ln.strip() and not ln.startswith("rem")]
    assert before[-1].startswith("goto "), (
        "the landing line must not be reached by falling through: "
        + before[-1])


def test_the_labels_older_copies_jump_to_still_exist():
    for name in KEPT_LABELS:
        assert f":{name}" in LINES, (
            f"FluBNF.bat lost :{name}. A copy that ran before an update ends a "
            "git call that can replace this file with `goto :" + name + "`, "
            "and goto looks the label up in the copy git left.")


def test_every_git_call_that_can_replace_this_file_ends_its_line_with_a_goto():
    """After the frozen lines, a merge, stash, reset or checkout that git
    may use to rewrite FluBNF.bat is followed on the SAME line by the goto:
    the next line would be read from the new copy at the old offset."""
    risky = ("git merge", "git stash push", "git stash pop", "git reset",
             "git checkout")
    offenders = [ln for ln in _update_block()
                 if ln.strip().startswith(risky) and "goto :" not in ln]
    assert not offenders, offenders


# ------------------------------------------------------ the self-update block
def test_a_clean_tree_is_never_told_local_edits_block_the_update():
    block = _update_block()
    text = "\n".join(block)
    dirty = block.index("for /f %%s in ('git status --porcelain -uno 2^>nul') "
                        'do set "DIRTY=1"')
    said = next(i for i, ln in enumerate(block)
                if "local edits are blocking the update" in ln)
    assert dirty < said
    # the only way to that message is a tracked edit
    assert "if defined DIRTY goto :updatedirty" in text
    assert block[said - 1] == ":updatedirty"
    # a clean tree shows git's own reason instead of stashing nothing
    clean = _after_label(text, "updatenotahead", "\n:updatedirty")
    assert "git stash" not in clean
    assert "git merge --ff-only -q origin/%BRANCH% && goto :uptodate" in clean


def test_only_a_stash_this_run_made_is_popped():
    block = _update_block()
    was = next(i for i, ln in enumerate(block) if 'set "STASHWAS=%%s"' in ln)
    push = next(i for i, ln in enumerate(block) if "git stash push" in ln)
    now = next(i for i, ln in enumerate(block) if 'set "STASHNOW=%%s"' in ln)
    pop = next(i for i, ln in enumerate(block) if "git stash pop" in ln)
    guard = block.index('if "%STASHNOW%"=="%STASHWAS%" goto :updatestuck')
    assert was < push < now < guard < pop, (
        "the stash pop is no longer guarded by refs/stash before and after "
        "this run's push, so a push that saved nothing pops an older stash")
    assert "refs/stash" in block[was] and "refs/stash" in block[now]


def test_recovery_commands_name_this_folder_one_per_line():
    """The console holds the launcher's window, so these are pasted into a
    new one (Command Prompt or PowerShell, whose 5.1 has no &&), which
    starts in the user's home folder."""
    shown = [ln for ln in _update_block()
             if ln.lstrip().startswith(("echo", "if defined DIRTY echo"))
             and "git " in ln and "echo   " in ln]
    commands = [ln for ln in shown if re.search(r"echo\s{7}git ", ln)]
    assert len(commands) >= 10, shown
    for ln in commands:
        assert 'git -C "%CD%" ' in ln, ln
        assert "&&" not in ln and "^&" not in ln, ln


def test_a_branch_gone_upstream_and_a_rewritten_history_are_named():
    text = "\n".join(_update_block())
    assert ('if /I not "%BRANCH%"=="main" git fetch -q --prune origin'
            in text), "a deleted branch's stale copy would read up to date"
    assert 'git rev-parse -q --verify "refs/remotes/origin/%BRANCH%"' in text
    gone = _after_label(text, "upstreamgone", "goto :deps")
    assert "no longer exists" in gone
    assert 'git -C "%CD%" checkout main' in gone
    assert ("git rev-list --left-only --cherry-pick --count "
            "HEAD...origin/%BRANCH%") in text
    rewritten = _after_label(text, "updaterewritten", "goto :deps")
    assert "nothing unique would be lost" in rewritten
    assert "throw this clone's work away" not in rewritten


def test_a_missing_git_is_said_out_loud():
    """Line 42 goes on silently when git is missing, and it is frozen; so
    the first lines after :deps say it, once per open."""
    after = LINES[_label_at("deps"):_label_at("gitchecked")]
    text = "\n".join(after)
    assert 'if not exist ".git" goto :gitchecked' in text
    assert 'if /I "%FLUBNF_UPDATE%"=="off" goto :gitchecked' in text
    assert "where git" in text
    said = [ln for ln in after if ln.startswith("if errorlevel 1 echo")]
    assert len(said) == 1 and "https://git-scm.com/download/win" in said[0]
    assert "cannot update itself or the engine" in said[0]


def test_the_first_run_prefers_the_pythons_ci_tests():
    """py -3 alone takes the newest Python installed, one Windows CI never
    runs and flubnf doctor calls untested; 3.12 and 3.11 come first, each
    tried only while there is no venv yet."""
    first = LINES[_label_at("firstrun"):_label_at("sync")]
    order = [next(i for i, ln in enumerate(first) if needle in ln)
             for needle in ("py -3.12 -m venv", "py -3.11 -m venv",
                            "py -3 -m venv", "python -m venv",
                            '"%CONDAPY%" -m venv')]
    assert order == sorted(order), order
    for i in order[1:]:
        # the `if` that opens the block holding this attempt
        guard = next(first[j] for j in range(i, -1, -1)
                     if first[j].startswith("if "))
        assert 'if not exist ".venv\\Scripts\\python.exe"' in guard, first[i]


def test_a_moved_folder_rebuilds_its_venv():
    """pip's .exe launchers hold the absolute path of the python.exe they
    were built with, so a folder moved by hand (setup.ps1 advises it under
    Controlled Folder Access) has a .venv whose programs no longer start."""
    check = "\n".join(LINES[_label_at("gitchecked"):_label_at("firstrun")])
    assert '".venv\\Scripts\\pip.exe" --version <nul >nul 2>&1' in check
    assert 'ren ".venv" ".venv.moved-%TS%"' in check
    assert 'if /I "%VENVAT%"=="%CD%" goto :sync' in check, (
        "the pip.exe check should run once per folder, not on every open")
    assert 'cd >".venv\\folder.stamp"' in check
    assert check.index("--version") < check.index('cd >".venv\\folder.stamp"')


def test_every_powershell_and_probe_reads_from_nul():
    """PowerShell waits for input that never comes when it inherits a pipe
    instead of a console (a CI runner, a scheduled task): every call the
    launcher makes, and the pip.exe probe, gets nul for input."""
    calls = [ln for ln in LINES
             if "powershell " in ln and not ln.lstrip().startswith("echo")]
    assert len(calls) >= 6, calls
    for ln in calls:
        assert "<nul" in ln, ln
    probe = next(ln for ln in LINES if "pip.exe\" --version" in ln)
    assert "<nul" in probe, probe


# ------------------------------------------------------------ the engine block
def test_a_named_engine_file_leaves_every_archive_variable_set():
    """FLUBNF_PYBNF_BUNDLE jumped past `set "ARCHIVES=0"`, and the unquoted
    `if %ARCHIVES% GTR 1` then ended the launcher before the console
    started, on every open. A named .tar.gz is an archive."""
    engine = _engine_section()
    shortcut = engine.index("if not defined FLUBNF_PYBNF_BUNDLE goto :bundlesearch")
    for init in ('set "BUNDLE="', 'set "ARCHIVE="', 'set "ARCHIVES=0"'):
        assert engine.index(init) < shortcut, init
    assert engine.count('set "ARCHIVES=0"') == 1
    assert 'if /I "%FLUBNF_PYBNF_BUNDLE:~-7%"==".tar.gz" goto :bundlenamedarchive' \
        in engine
    named = _after_label(engine, "bundlenamedarchive", "goto :")
    assert 'set "ARCHIVE=%FLUBNF_PYBNF_BUNDLE%"' in named
    assert 'set "ARCHIVES=1"' in named


def test_the_engine_probes_take_the_folder_as_an_argument():
    """Spliced into r'...', an apostrophe in the path (C:\\Users\\O'Neil) or a
    trailing backslash was a SyntaxError that read as "not installed"."""
    assert "r'%PYBNFDIR%'" not in BAT
    probes = [ln for ln in LINES if "from pybnf.pf import ParticleFilter" in ln
              and ln.startswith('"%ENGINEPY%" -c')]
    assert len(probes) == 2, probes
    for ln in probes:
        assert "sys.path.insert(0, sys.argv[1])" in ln
        assert re.search(r'" "%PYBNFDIR%"( >nul 2>&1)?$', ln), ln
    # stripped once, from the recorded value, before anything uses it
    strip = LINES.index('if "%PYBNFDIR:~-1%"=="\\" set "PYBNFDIR=%PYBNFDIR:~0,-1%"')
    assert LINES.index("if not defined PYBNFDIR goto :pybnfprobe") < strip \
        < LINES.index('if exist "%PYBNFDIR%\\.git" goto :pybnfresolved')


def test_git_gates_only_the_bundle_clone():
    """An archive unpacks with Windows' tar and a checkout needs no git to
    install, so only the bundle clone may stop at :enginenogit."""
    engine = _engine_section()
    after = _after_label(engine, "perldone")
    assert after.index('if exist "%PYBNFDIR%\\pybnf\\pf.py" goto :enginevenv') \
        < after.index("goto :enginenogit") < after.index("git bundle verify")
    nogit = _after_label(engine, "enginenogit", "goto :")
    assert "https://git-scm.com/download/win" in nogit
    assert "tar.gz" in nogit, "the no-git remedy should offer the archive"


def test_the_attempt_fingerprint_moves_with_a_new_archive():
    fp = [ln for ln in LINES if ln.startswith('set "ENGINEFP=')]
    assert len(fp) == 1, fp
    assert "%ARCHIVE%" in fp[0] and "%ARCHIVESZ%" in fp[0]
    assert 'if defined ARCHIVE for %%F in ("%ARCHIVE%") do set "ARCHIVESZ=%%~zF"' \
        in LINES


def test_the_retry_text_promises_only_what_happens():
    """Running setup.ps1 changes nothing the stamp looks at, and the stamp is
    now honoured only with nothing here to install from."""
    assert "setup.ps1, starts it again" not in BAT
    assert "Run setup.ps1 to see why" not in BAT
    assert 'set "ATTEMPT=%CD%\\.venv\\engine-attempt.txt"' in LINES
    failed = _after_label(BAT, "enginefailed", "goto :")
    assert "the next open tries again" in " ".join(
        ln.replace("echo", "").strip() for ln in failed.split("\r\n"))
    skipped = _after_label(BAT, "engineskipped", "\r\n:startconsole")
    assert '"%ATTEMPT%"' in skipped


def test_a_verified_engine_is_written_back_where_it_was_recorded():
    """setup.ps1 records its default before any engine exists; flubnf doctor
    and the CLI in a new window follow that record. After a verified engine
    the launcher writes the folder back when the record says otherwise."""
    rec = LINES.index('set "PYBNFREC=%FLUBNF_PYBNF%"')
    assert rec < LINES.index('set "PYBNFDIR=%FLUBNF_PYBNF%"')
    assert rec < LINES.index('set "FLUBNF_PYBNF=%PYBNFDIR%"'), (
        "the record must be read before the engine block sets its own")
    assert 'set "ENGINEREC=%FLUBNF_PY_ENGINE%"' in LINES
    calls = [i for i, ln in enumerate(LINES) if ln == "call :recordengine"]
    assert len(calls) == 2, "the ENGINEOK path and a finished install"
    assert LINES[calls[0] - 1] == 'set "ENGINEOK=1"'
    assert LINES[calls[1] - 1] == 'set "FLUBNF_PYBNF=%PYBNFDIR%"'
    sub = "\n".join(LINES[_label_at("recordengine"):_label_at("newerarchive")])
    # nothing recorded: nothing written (a normal machine sees nothing)
    assert 'if defined PYBNFREC if /I not "%PYBNFREC%"=="%PYBNFDIR%"' in sub
    assert 'if defined ENGINEREC if /I not "%ENGINEREC%"=="%ENGINEPY%"' in sub
    assert 'setx FLUBNF_PYBNF "%PYBNFDIR%" >nul 2>&1' in sub
    assert 'setx FLUBNF_PY_ENGINE "%ENGINEPY%" >nul 2>&1' in sub
    assert 'echo set "FLUBNF_PYBNF=%PYBNFDIR%">>".flubnf.env.cmd"' in sub
    assert sub.rstrip().endswith("goto :eof")


# ---------------------------------------------------- run with cmd.exe (Windows)
GIT_ENV = {"GIT_AUTHOR_NAME": "T", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "T", "GIT_COMMITTER_EMAIL": "t@example.invalid",
           "GIT_TERMINAL_PROMPT": "0"}


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV},
                          text=True, capture_output=True, check=True,
                          timeout=60)


def _cmd(script: Path, text: str, cwd: Path, **env_extra) -> subprocess.CompletedProcess:
    # .bat, not .cmd: `set` keeps ERRORLEVEL in a .bat, as in FluBNF.bat
    script.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n")
                       .encode("ascii"))
    root = os.environ.get("SystemRoot", r"C:\Windows")
    env = {**os.environ, **GIT_ENV,
           # Windows' own tar first: Git's usr\bin has a GNU tar that reads
           # C: as a host name, which a normal machine never has on PATH
           "PATH": rf"{root}\System32;" + os.environ.get("PATH", "")}
    env.pop("FLUBNF_UPDATE", None)
    env.update(env_extra)
    # stdin closed: a program that waits on an inherited pipe (PowerShell
    # does) would otherwise hold the test to its timeout
    return subprocess.run(["cmd", "/d", "/c", str(script)], cwd=cwd, env=env,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          text=True, errors="replace", timeout=180,
                          check=False)


def _said(r: subprocess.CompletedProcess) -> str:
    return f"exit {r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}"


def _commands(out: str) -> list[tuple[Path, str]]:
    """The printed `git -C "<folder>" ...` commands, folder resolved: %CD%
    can be the 8.3 short form (RUNNER~1) of tmp_path."""
    return [(Path(m.group(1)).resolve(), m.group(2).strip())
            for m in re.finditer(r'git -C "([^"]+)" ([^\r\n]+)', out)]


def _origin_and_clone(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A bare origin one commit ahead of a clone, both on main, with no
    line-ending conversion (bytes compare exactly)."""
    work = tmp_path / "work"
    work.mkdir()
    _git(work, "-c", "init.defaultBranch=main", "init", "-q", ".")
    _git(work, "config", "core.autocrlf", "false")
    (work / "app.py").write_bytes(b"v1\n")
    _git(work, "add", "app.py")
    _git(work, "commit", "-qm", "v1")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "clone", "-q", "--bare", str(work), str(origin))
    clone = tmp_path / "clone"
    _git(tmp_path, "clone", "-q", "-c", "core.autocrlf=false", str(origin),
         str(clone))
    (work / "app.py").write_bytes(b"v2\n")
    _git(work, "commit", "-qam", "v2")
    _git(work, "push", "-q", str(origin), "main")
    return work, origin, clone


def _run_update(tmp_path: Path, clone: Path) -> subprocess.CompletedProcess:
    start = BAT.index("rem Stay current (lab-share mode).")
    end = re.search(r"^:deps\r?$", BAT, re.MULTILINE).start()
    text = ("@echo off\nsetlocal\n" + BAT[start:end]
            + ":deps\necho REACHED-DEPS\nexit /b 0\n")
    return _cmd(tmp_path / "update-block.bat", text, clone)


def _stashes(clone: Path) -> list[str]:
    return _git(clone, "stash", "list").stdout.splitlines()


@windows_only
def test_windows_a_clean_clone_fast_forwards(tmp_path):
    _, _, clone = _origin_and_clone(tmp_path)
    r = _run_update(tmp_path, clone)
    assert "up to date with origin" in r.stdout, _said(r)
    assert "REACHED-DEPS" in r.stdout, _said(r)
    assert (clone / "app.py").read_bytes() == b"v2\n", _said(r)


@windows_only
def test_windows_a_stray_edit_is_stashed_and_the_update_goes_through(tmp_path):
    _, _, clone = _origin_and_clone(tmp_path)
    (clone / "app.py").write_bytes(b"someone edited this\n")
    r = _run_update(tmp_path, clone)
    assert "local edits are blocking the update" in r.stdout, _said(r)
    assert "app.py" in r.stdout, _said(r)
    assert "updated anyway" in r.stdout, _said(r)
    assert (clone / "app.py").read_bytes() == b"v2\n", _said(r)
    assert any("FluBNF update" in s for s in _stashes(clone)), (
        "the edit was destroyed, not set aside\n" + _said(r))


@windows_only
def test_windows_a_clean_clone_blocked_by_an_untracked_file_keeps_an_older_stash(
        tmp_path):
    """Upstream starts tracking a file this clone has untracked. Nothing is
    edited, so nothing may be stashed, and the older stash on the list (the
    launcher's own, from a month ago) must not be popped into the tree."""
    work, origin, clone = _origin_and_clone(tmp_path)
    (clone / "app.py").write_bytes(b"an older edit, set aside\n")
    _git(clone, "stash", "push", "-q", "-m", "older")
    (work / "new.py").write_bytes(b"upstream\n")
    _git(work, "add", "new.py")
    _git(work, "commit", "-qm", "v3")
    _git(work, "push", "-q", str(origin), "main")
    (clone / "new.py").write_bytes(b"mine\n")

    r = _run_update(tmp_path, clone)

    assert "local edits are blocking" not in r.stdout, _said(r)
    assert "could not update" in r.stdout, _said(r)
    assert (clone.resolve(), "reset --hard origin/main") in _commands(r.stdout), \
        _said(r)
    assert (clone / "app.py").read_bytes() == b"v1\n", (
        "an older stash was popped into a clean tree\n" + _said(r))
    assert (clone / "new.py").read_bytes() == b"mine\n", _said(r)
    stashes = _stashes(clone)
    assert len(stashes) == 1 and "older" in stashes[0], stashes
    assert "REACHED-DEPS" in r.stdout, _said(r)


@windows_only
def test_windows_a_rewritten_history_says_nothing_unique_would_be_lost(tmp_path):
    work, origin, clone = _origin_and_clone(tmp_path)
    _git(clone, "pull", "-q", "--ff-only")
    _git(work, "commit", "-q", "--amend", "-m", "v2, reworded upstream")
    _git(work, "push", "-q", "--force", str(origin), "main")
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()

    r = _run_update(tmp_path, clone)

    assert "nothing unique would be lost" in r.stdout, _said(r)
    assert "throw this clone's work away" not in r.stdout, _said(r)
    assert (clone.resolve(), "reset --hard origin/main") in _commands(r.stdout), \
        _said(r)
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == head


@windows_only
def test_windows_a_branch_deleted_upstream_names_main(tmp_path):
    work, origin, clone = _origin_and_clone(tmp_path)
    _git(work, "push", "-q", str(origin), "main:feature")
    _git(clone, "fetch", "-q")
    _git(clone, "checkout", "-q", "-b", "feature", "--track", "origin/feature")
    _git(work, "push", "-q", str(origin), "--delete", "feature")
    head = _git(clone, "rev-parse", "HEAD").stdout.strip()

    r = _run_update(tmp_path, clone)

    assert "origin/feature no longer exists" in r.stdout, _said(r)
    assert (clone.resolve(), "checkout main") in _commands(r.stdout), _said(r)
    assert _git(clone, "rev-parse", "HEAD").stdout.strip() == head
    assert _stashes(clone) == []


def _engine_file_block() -> str:
    start = BAT.index("\r\n:engineabsent\r\n") + 2
    end = BAT.index("\r\n:archivedone\r\n") + 2
    sub = BAT.index("\r\n:newerarchive\r\n") + 2
    stop = BAT.find("\r\n\r\n", sub)
    return ("@echo off\nsetlocal\n" + BAT[start:end] + ":archivedone\n"
            "echo ARCHIVE=[%ARCHIVE%] BUNDLE=[%BUNDLE%]\n"
            "echo REACHED\nexit /b 0\n\n"
            + (BAT[sub:] if stop < 0 else BAT[sub:stop + 2]))


@windows_only
@pytest.mark.parametrize("name", ["pybnf.bundle", "pybnf-pf-1a2b3c4d.tar.gz"])
def test_windows_a_named_engine_file_reaches_the_end_of_the_search(tmp_path, name):
    """FLUBNF_PYBNF_BUNDLE, as docs/ENGINE.md suggests for a file on a USB
    stick. Either shape must get through the search with no IF syntax error
    (which ends the whole launcher), and a .tar.gz is unpacked as an
    archive, not verified as a git bundle."""
    usb = tmp_path / "usb"
    usb.mkdir()
    named = usb / name
    if name.endswith(".tar.gz"):
        src = tmp_path / "src" / "PyBNF-Private"
        (src / "pybnf").mkdir(parents=True)
        (src / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
        (src / "VERSION").write_text("pf/pre-pr 1a2b3c4d\n")
        with tarfile.open(named, "w:gz") as tar:
            tar.add(src, arcname="PyBNF-Private")
    else:
        named.write_bytes(b"not opened by this block")
    home, local = tmp_path / "home", tmp_path / "local"
    home.mkdir()
    local.mkdir()
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()

    r = _cmd(slice_dir / "engine-file.bat", _engine_file_block(), slice_dir,
             USERPROFILE=str(home), LOCALAPPDATA=str(local),
             OneDrive=str(tmp_path / "no-onedrive"),
             PYBNFDIR=str(local / "FluBNF" / "PyBNF-pf"),
             FLUBNF_PYBNF_BUNDLE=str(named))

    assert r.returncode == 0, _said(r)
    assert "REACHED" in r.stdout, _said(r)
    assert "was unexpected" not in r.stdout + r.stderr, _said(r)
    if name.endswith(".tar.gz"):
        assert f"ARCHIVE=[{named}] BUNDLE=[]" in r.stdout, _said(r)
        assert "unpacking the engine from" in r.stdout, _said(r)
        assert (local / "FluBNF" / "PyBNF-Private" / "pybnf" / "pf.py").is_file()
    else:
        assert f"ARCHIVE=[] BUNDLE=[{named}]" in r.stdout, _said(r)


def _moved_block() -> str:
    start = BAT.index("\r\n:deps\r\n") + 2
    end = BAT.index("\r\n:firstrun\r\n") + 2
    return ("@echo off\nsetlocal\n" + BAT[start:end]
            + ":firstrun\necho REACHED-FIRSTRUN\nexit /b 0\n"
            + ":sync\necho REACHED-SYNC\nexit /b 0\n"
            + ":fail\necho REACHED-FAIL\nexit /b 1\n")


@windows_only
def test_windows_a_moved_folder_sets_its_venv_aside_and_sets_up_again(tmp_path):
    folder = tmp_path / "flubnf"
    scripts = folder / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "flubnf.exe").write_bytes(b"")
    # a real program that starts and fails on --version, as a moved venv's
    # pip.exe does ("Fatal error in launcher"); an empty file is no program
    # at all and could stop at a Windows error box
    root = os.environ.get("SystemRoot", r"C:\Windows")
    shutil.copy(Path(root) / "System32" / "where.exe", scripts / "pip.exe")

    r = _cmd(tmp_path / "moved.bat", _moved_block(), folder)

    assert "REACHED-FIRSTRUN" in r.stdout, _said(r)
    assert not (folder / ".venv").exists(), _said(r)
    kept = list(folder.glob(".venv.moved-*"))
    assert len(kept) == 1 and (kept[0] / "Scripts" / "flubnf.exe").exists()


@windows_only
def test_windows_a_venv_checked_here_before_is_not_checked_again(tmp_path):
    folder = tmp_path / "flubnf"
    scripts = folder / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    (scripts / "flubnf.exe").write_bytes(b"")
    (scripts / "pip.exe").write_bytes(b"")
    # written as the launcher writes it, so it spells %CD% the same way
    here = subprocess.run(["cmd", "/d", "/c", "cd"], cwd=folder,
                          stdin=subprocess.DEVNULL, capture_output=True,
                          timeout=60, check=True).stdout
    (folder / ".venv" / "folder.stamp").write_bytes(here)

    r = _cmd(tmp_path / "moved.bat", _moved_block(), folder)

    assert "REACHED-SYNC" in r.stdout, _said(r)
    assert (scripts / "flubnf.exe").exists(), _said(r)
