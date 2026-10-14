"""FluBNF.bat, the Windows launcher: its self-update, the engine file, the
Perl check and the engine venv.

cmd.exe reads a batch file as it runs it. When the `git merge` on line 65
replaces FluBNF.bat, cmd carries on at the same byte offset in the new copy,
so the bytes an update resumes at are pinned here, on every platform. The
new blocks are checked as text everywhere; on Windows they are also sliced
out of FluBNF.bat and run with cmd.exe against real clones, as
tests/test_launcher_update.py runs FluBNF.command's. Programs the blocks
start (perl, winget, py, python) are stand-in .exe files on a PATH of the
test's own, so nothing is installed and no network is used.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

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


# ------------------------------------------------------- Perl (:perlblock)
def _perlblock_lines() -> list[str]:
    """:perlblock, the last subroutine in FluBNF.bat, to the end of file."""
    return LINES[_label_at("perlblock"):]


def _code(lines: list[str]) -> list[str]:
    return [ln for ln in lines if ln.strip() and not ln.startswith("rem ")]


def test_the_perl_offer_is_made_once_on_its_own_record():
    """A declined or failed winget must not be back on every open, and an
    offer never made must not be skipped. engine-attempt.txt also stamps an
    engine file that did not unpack, so a retry skipped the question though
    nobody had been asked: the offer has a record of its own."""
    block = _perlblock_lines()
    assert 'set "PERLOFFER=%CD%\\.venv\\perl-offer.txt"' in block
    gate = block.index('if exist "%PERLOFFER%" goto :perlreminder')
    ask = next(k for k, ln in enumerate(block) if ln.startswith("choice "))
    run = next(k for k, ln in enumerate(block)
               if ln.startswith("winget install"))
    assert gate < ask < run
    assert not any("%ATTEMPT%" in ln for ln in block), (
        "the Perl offer is gated on the engine's attempt stamp again")
    # the question itself is as before: 20 s, Y when nobody answers
    assert "/t 20 /d Y" in block[ask]
    # every way the offer ends writes the record, except another install
    # in progress, which asks again on the next open
    writes = [ln for ln in block if ln.endswith('>"%PERLOFFER%"')]
    assert writes == ['echo "%PERLSAID%">"%PERLOFFER%"',
                      'echo "no winget">"%PERLOFFER%"',
                      'echo "installed">"%PERLOFFER%"'], writes
    busy = _after_label("\r\n".join(block), "perlbusy", "\r\n:")
    assert "PERLOFFER" not in busy and busy.rstrip().endswith("goto :eof")
    # afterwards: the two-line reminder, with the link and the way for an
    # account that is not an administrator
    reminder = _code(_after_label("\r\n".join(block), "perlreminder",
                                  "goto :eof").split("\r\n"))
    assert len(reminder) == 2, reminder
    assert "Perl is still missing" in reminder[0]
    assert "https://strawberryperl.com" in reminder[1]
    assert "not an administrator" in reminder[1]


def test_every_open_reaches_the_perl_check():
    """The offer lived inside the engine install alone: once the engine
    imported (ENGINEOK jumps to the console), with no engine file, or after
    one that did not unpack, no open said a word about Perl."""
    done = LINES.index(":archivedone")
    after = _code(LINES[done + 1:done + 6])
    assert after[:2] == ["if defined ENGINEOK call :perlblock",
                         "if defined ENGINEOK goto :startconsole"], after
    calls = [i for i, ln in enumerate(LINES) if ln == "call :perlblock"]
    # the ENGINEOK call is under `if defined`; these are the other four
    assert len(calls) == 4, calls
    nothing = BAT[BAT.index("echo   PF engine not installed"):
                  BAT.index("\r\n:engineinstall\r\n")]
    assert nothing.index("call :perlblock") < nothing.index("goto :startconsole")
    assert "call :perlblock" in _after_label(BAT, "engineskipped",
                                             "\r\n:startconsole\r\n")
    assert "call :perlblock" in _after_label(BAT, "enginebadarchive",
                                             "goto :")
    install = _after_label(BAT, "engineinstall", "\r\n:enginevenv\r\n")
    assert install.index("goto :enginebadarchive") \
        < install.index("call :perlblock")
    assert "winget" not in _engine_section(), (
        "Perl belongs in :perlblock, so another way to get it drops in once")
    assert "  echo Trying the particle filter engine install again, a few minutes." in install


def test_perlblock_returns_and_never_runs_into_another_label():
    """Reached with `call`: every way out is `goto :eof`, and the last line
    of the file is one, so it cannot fall through into a subroutine below.
    Every jump inside stays inside."""
    block = _perlblock_lines()
    assert _code(block)[-1] == "goto :eof"
    assert LINES[-1] == "goto :eof" or (LINES[-1] == "" and LINES[-2] == "goto :eof")
    own = {ln[1:] for ln in block if ln.startswith(":")}
    for ln in _code(block):
        for target in re.findall(r"goto :(\w+)", ln):
            assert target == "eof" or target in own, ln
    # no other subroutine starts after it
    assert all(not ln.startswith(":") or ln[1:] in own for ln in block)
    # and no parenthesised block, where %WG% would expand before winget ran
    assert not [ln for ln in _code(block) if ln.endswith("(")
                or ln.lstrip().startswith(")")]


def test_only_a_windows_perl_counts():
    """Git's Unix tools, MSYS2 and Cygwin bring a perl whose $^O is msys or
    cygwin; BNG2.pl cannot load its modules under it. A Strawberry Perl on
    disk but off this window's PATH is put on it, in its installer's order,
    and nothing is offered."""
    block = _code(_perlblock_lines())
    probe = ('perl.exe -e "exit($^O eq q(MSWin32) ? 0 : 1)" <nul >nul 2>&1 '
             '&& goto :eof')
    assert block[1] == probe, block[:3]
    assert "where perl >nul" not in BAT
    onpath = block.index('if exist "%SystemDrive%\\Strawberry\\perl\\bin\\perl.exe" '
                         'goto :perloffpath')
    assert onpath < next(i for i, ln in enumerate(block)
                         if ln.startswith("where winget"))
    folders = ('set "PATH=%SystemDrive%\\Strawberry\\c\\bin;'
               '%SystemDrive%\\Strawberry\\perl\\site\\bin;'
               '%SystemDrive%\\Strawberry\\perl\\bin;%PATH%"')
    assert [ln for ln in LINES if "Strawberry\\c\\bin" in ln
            and not ln.startswith("rem ")] == [folders]


def test_winget_is_judged_by_the_disk_not_by_errorlevel():
    """winget's failure codes are negative (0x8A15xxxx), and `if errorlevel 1`
    means 1 or more: a declined permission prompt went down the success path
    and printed "Perl installed". The code is kept, on its own line outside
    any parenthesised block, and success is perl.exe on disk."""
    block = _code(_perlblock_lines())
    runs = [i for i, ln in enumerate(block) if ln.startswith("winget ")]
    assert len(runs) == 1
    run = runs[0]
    assert block[run + 1] == 'set "WG=%ERRORLEVEL%"'
    assert block[run + 2] == ('if exist "%SystemDrive%\\Strawberry\\perl\\bin'
                              '\\perl.exe" goto :perlinstalled')
    for ln in block[run:]:
        assert "errorlevel" not in ln.lower() or ln == 'set "WG=%ERRORLEVEL%"', ln
    assert "Perl installed. This window cannot see it yet" not in BAT
    # the codes a student is most likely to meet, each with its own words
    for code in ("-1978334964", "-1978334974", "-1978334961", "-1978335174"):
        assert any(ln.startswith(f'if "%WG%"=="{code}" goto :perl')
                   for ln in block), code


def test_the_permission_prompt_is_announced_before_winget_runs():
    """Strawberry is a machine-wide MSI: Windows asks for permission, behind
    another window as a flashing taskbar button, and a non-administrator
    account needs an administrator's password. Nothing used to say so."""
    block = _code(_perlblock_lines())
    run = next(i for i, ln in enumerate(block) if ln.startswith("winget "))
    said = " ".join(ln for ln in block[:run] if ln.startswith("echo"))
    for words in ("Windows will ask permission", "about 210 MB", "Click Yes",
                  "flashing shield on the taskbar",
                  "needs an administrator's password"):
        assert words in said, words


def test_every_winget_command_names_the_winget_source():
    """Without --source winget, winget also searches the msstore source, and
    when that cannot be reached the install stops although the package was
    found. setup.ps1 ran with it; FluBNF.bat and the commands setup.ps1
    prints for later did not."""
    ps1 = (REPO / "setup.ps1").read_text(encoding="utf-8")
    found = [ln for ln in (BAT + "\n" + ps1).splitlines()
             if "winget install" in ln and not ln.lstrip().startswith(("rem", "#"))]
    assert len(found) == 4, found
    for ln in found:
        assert "--source winget" in ln, ln
        assert "StrawberryPerl.StrawberryPerl" in ln and " -e" in ln, ln
    bat_run = next(ln for ln in LINES if ln.startswith("winget install"))
    assert "--accept-source-agreements --accept-package-agreements" in bat_run
    assert "--disable-interactivity" not in BAT, (
        "older App Installer builds refuse that flag with a negative code")


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
    # the open's, a replaced copy's (:archivereplaced), the install's
    assert len(probes) == 3, probes
    for ln in probes:
        assert "sys.path.insert(0, sys.argv[1])" in ln
        assert re.search(r'" "%PYBNFDIR%"( (<nul )?>nul 2>&1)?$', ln), ln
    # stripped once, from the recorded value, before anything uses it
    strip = LINES.index('if "%PYBNFDIR:~-1%"=="\\" set "PYBNFDIR=%PYBNFDIR:~0,-1%"')
    assert LINES.index("if not defined PYBNFDIR goto :pybnfprobe") < strip \
        < LINES.index('if exist "%PYBNFDIR%\\.git" goto :pybnfresolved')


def test_git_gates_only_the_bundle_clone():
    """An archive unpacks with Windows' tar and a checkout needs no git to
    install, so only the bundle clone may stop at :enginenogit."""
    engine = _engine_section()
    install = _after_label(engine, "engineinstall")
    after = install[install.index("call :perlblock"):]
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


def test_no_version_stamp_is_read_with_set_p():
    """VERSION is cut on a Mac with LF line ends. set /p reads up to a CR LF,
    so it took all three lines, and the line breaks it carried into the IF
    that compares the stamps ended the launcher on every open with the
    engine file still in Downloads. for /f splits on LF; `if not defined`
    keeps the first line, so each variable is cleared before its read."""
    offenders = [ln for ln in LINES if not ln.startswith("rem ")
                 and "set /p" in ln.lower() and "version" in ln.lower()]
    assert not offenders, offenders
    for name in ("OLDVER", "FLUVER"):
        read = (f'if exist "%PYBNFDIR%\\VERSION" for /f "usebackq delims=" '
                f'%%V in ("%PYBNFDIR%\\VERSION") do if not defined {name} '
                f'set "{name}=%%V"')
        assert read in LINES, f"{name} is no longer read with for /f"
        cleared = max(i for i, ln in enumerate(LINES[:LINES.index(read)])
                      if ln == f'set "{name}="')
        assert LINES.index(read) - cleared < 15, (
            f"{name} is not cleared just before it is read")
    # the archive's stamp: by its member name, which the unpack requires
    stale = _after_label(BAT, "archivestale", "\r\n:archivereplace\r\n")
    assert ('(`tar -xzOf "%ARCHIVE%" PyBNF-Private/VERSION 2^>nul`) '
            'do if not defined NEWVER set "NEWVER=%%V"') in stale
    assert "findstr" not in stale and "VMEMBER" not in BAT


def test_a_replaced_engine_is_probed_again_and_installed_if_it_does_not_import():
    """ENGINEOK came from probing the copy that was just set aside; kept, it
    sent the new copy to the console with no import check. Cleared every
    time, it sent a new copy that imports through pip, and a network without
    PyPI was told the engine was missing while the console ran it. The new
    copy gets this open's own probe, and only a failure clears ENGINEOK."""
    probe = ('"%ENGINEPY%" -c "import sys; sys.path.insert(0, sys.argv[1]); '
             'import bngsim; from pybnf.pf import ParticleFilter" "%PYBNFDIR%"')
    first = LINES[:LINES.index(":engineabsent")]
    assert [ln for ln in first if ln.startswith(probe)] == [
        probe + " >nul 2>&1"], "the open's own probe changed; match it below"
    replaced = _after_label(BAT, "archivereplaced", "\r\n:archiveunpacked\r\n")
    body = [ln for ln in replaced.split("\r\n")
            if ln and not ln.startswith("rem ")]
    # ERRORLEVEL against 0: a crash exits negative, which `if errorlevel 1`
    # reads as success
    assert body[1:] == ["if not defined ENGINEOK goto :archiveunpacked",
                        probe + " <nul >nul 2>&1",
                        'if not "%ERRORLEVEL%"=="0" set "ENGINEOK="'], body
    done = LINES.index(":archivedone")
    gate = [ln for ln in LINES[done + 1:done + 6] if not ln.startswith("rem ")]
    # the Perl check first (test_every_open_reaches_the_perl_check)
    assert gate[:2] == ["if defined ENGINEOK call :perlblock",
                        "if defined ENGINEOK goto :startconsole"], gate


def test_only_the_lab_engine_file_counts_and_a_miss_names_the_folders():
    """PyPI's pybnf-<version>.tar.gz and GitHub's PyBNF-<version>.tar.gz
    matched pybnf*.tar.gz and, being newer, won. When nothing is found the
    launcher names every folder it looked in: a Downloads folder moved
    elsewhere, or a file one folder down, was a miss with nothing on screen
    to say where the file should go."""
    assert "pybnf*.tar.gz" not in BAT
    loops = [ln for ln in LINES if "pybnf-pf-*.tar.gz" in ln
             and ln.lstrip().startswith(("for ", "if defined OneDrive for "))]
    assert len(loops) == 8, loops
    calls = [ln for ln in LINES if ln.startswith("call :enginelookedin")]
    assert calls == ['call :enginelookedin "%~dp0."'] * 2, calls
    nothing = BAT[BAT.index("echo   PF engine not installed"):
                  BAT.index("\r\n:engineinstall\r\n")]
    assert "call :enginelookedin" in nothing
    assert "call :enginelookedin" in _after_label(
        BAT, "engineskipped", "\r\n:startconsole\r\n")
    sub = _after_label(BAT, "enginelookedin", "goto :eof")
    for folder in ('"%~1"', '"%~1\\.."', '"%USERPROFILE%\\Downloads"',
                   '"%USERPROFILE%\\Desktop"', '"%USERPROFILE%\\Documents"'):
        assert folder in sub, folder
    assert ('if defined OneDrive for %%D in ("%OneDrive%\\Downloads" '
            '"%OneDrive%\\Desktop" "%OneDrive%\\Documents")') in sub


def test_a_venv_missing_bionetgen_is_refreshed_even_when_the_stamp_matches():
    """:firstrun installs flubnf and bionetgen in one pip call; pip puts
    flubnf.exe in before the Jupyter stack bionetgen brings, so a first run
    closed late left a .venv that skipped :firstrun from then on, with no
    BNG2.pl for Check or the Sandbox."""
    sync = LINES[_label_at("sync"):_label_at("data")]
    missing = sync.index('if not exist ".venv\\Lib\\site-packages\\bionetgen'
                         '\\bng-win\\BNG2.pl" goto :syncbng')
    assert missing < next(i for i, ln in enumerate(sync)
                          if ln.startswith("fc /b pyproject.toml"))
    pip = [ln for ln in sync if ln.startswith('".venv\\Scripts\\pip" install')]
    assert pip == ['".venv\\Scripts\\pip" install -q -e ".[app,dev]" bionetgen']
    # a failed refresh still reaches the console
    assert "  echo   dependency refresh failed - running with what is installed" \
        in sync


# ------------------------------------------------------- the engine venv block
# Lines 1-65 hold CONDAPY's first four folders and are frozen.
FROZEN_LINES = BAT_BYTES[:FROZEN_END].count(b"\r\n")
CONDA_FOLDERS = [r"%USERPROFILE%\anaconda3", r"%USERPROFILE%\miniconda3",
                 r"%LOCALAPPDATA%\anaconda3", r"%ProgramData%\anaconda3",
                 r"%LOCALAPPDATA%\miniconda3", r"%ProgramData%\miniconda3",
                 r"%USERPROFILE%\miniforge3", r"%SystemDrive%\anaconda3",
                 r"%SystemDrive%\anaconda"]


def _engine_venv_lines() -> list[str]:
    """:enginevenv through the probe's failure text, up to the labels for
    an engine file that did not unpack or clone."""
    return LINES[_label_at("enginevenv"):_label_at("enginebadbundle")]


def _conda_search() -> list[str]:
    """The lines after :gitchecked that find conda, before the first gate."""
    return LINES[_label_at("gitchecked") + 1:LINES.index(
        'if not exist ".venv\\Scripts\\flubnf.exe" goto :firstrun')]


def _gate() -> str:
    line = next(ln for ln in LINES if ln.startswith('set "ENGINEGATE='))
    assert line.endswith('"'), line
    return line[len('set "ENGINEGATE='):-1]


def test_no_engine_venv_failure_is_silent():
    """With no Python 3.11/3.12 and no Anaconda in the four folders it knew,
    the window said only "Engine setup did not finish (see above)" with
    nothing above it, on every open. Every jump to :enginefailed in the
    block now comes straight after its own cause and one step to take, and
    none hides behind an IF."""
    block = _engine_venv_lines()
    jumps = [i for i, ln in enumerate(block) if "goto :enginefailed" in ln]
    assert len(jumps) == 10, [block[i - 1] for i in jumps]
    for i in jumps:
        assert block[i] == "goto :enginefailed", block[i]
        said = []
        for ln in reversed(block[:i]):
            if ln.startswith("rem "):
                continue
            if not ln.startswith("echo "):
                break
            said.insert(0, ln[len("echo "):].strip())
        assert said, f"nothing printed before line {i}: {block[i - 1]}"
        text = " ".join(" ".join(said).split()).lower()
        assert "open flubnf again" in text, text


def test_every_python_the_engine_venv_is_made_from_passes_one_gate():
    """numpy<2, bngsim and libroadrunner have Windows wheels for x64 only. A
    version check let an ARM64 or 32-bit 3.12 through, and pip then ended in
    a compiler error on every open. An existing venv, each candidate in the
    order it always had (decision D3), and the Python conda makes all go
    through ENGINEGATE, which checks the build as well as the version, and
    a Python is used only after the gate said 0."""
    gate = _gate()
    assert "sysconfig.get_platform()" in gate and "'win-amd64'" in gate
    assert "v[:2] in ((3,11),(3,12))" in gate
    code = _code(_engine_section().split("\r\n"))
    assert sum("((3,11),(3,12))" in ln for ln in code) == 1, (
        "a version check other than ENGINEGATE is left in the engine block")
    block = _engine_venv_lines()
    calls = [ln for ln in block if ' -c "%ENGINEGATE%" ' in ln]
    assert [ln.split(' -c "%ENGINEGATE%"')[0] for ln in calls] == [
        '"%ENGINEPY%"', "py -3.12", "py -3.11", "python", '"%CONDAPY%"',
        '"%CONDAENV%\\python.exe"']
    for ln in calls:
        assert ln.endswith(" <nul 2>nul"), ln
    chosen = [ln for ln in block if 'set "MAKEEXE=' in ln
              and ln != 'set "MAKEEXE="']
    assert len(chosen) == 5, chosen
    for ln in chosen:
        assert ln.startswith(('if "%GATE%"=="0" ', 'if "%ERRORLEVEL%"=="0" ')), ln
    made = [ln for ln in _code(block) if "-m venv" in ln
            and not ln.startswith("echo")]
    assert made == ['"%MAKEEXE%" %MAKEARG% -m venv "%ENGINEVENV%"'], made
    # a negative exit (a crash) is not success: no errorlevel test after a gate
    for i, ln in enumerate(block):
        if ' -c "%ENGINEGATE%" ' in ln:
            assert not block[i + 1].startswith("if not errorlevel"), block[i + 1]


def test_an_existing_venv_that_does_not_start_is_not_called_too_new():
    """A venv whose base Python was removed exits 103 ("No Python at"), and
    the launcher said its Python was too new. The gate's codes tell the
    cases apart: 2 another version, 3 another processor, else no start."""
    block = _engine_venv_lines()
    first = block.index('"%ENGINEPY%" -c "%ENGINEGATE%" "the engine venv" <nul 2>nul')
    assert block[first + 1:first + 5] == [
        'set "GATE=%ERRORLEVEL%"',
        'if "%GATE%"=="2" goto :enginevenvrebuild',
        'if "%GATE%"=="3" goto :enginevenvrebuild',
        'if not "%GATE%"=="0" goto :enginevenvgone']
    gone = "\n".join(_code(_after_label(
        "\r\n".join(block), "enginevenvgone", ":enginevenvrebuild").splitlines()))
    assert "does not start" in gone and "too new" not in gone
    assert "too new" not in "\n".join(_code(block))


def test_a_venv_without_pip_is_rebuilt_and_pip_runs_through_python():
    """A venv whose ensurepip never finished passed the version check, and
    every open then failed at "No module named pip" and "'pip' is not
    recognized". pip is checked after the gate, a new venv's failed
    ensurepip is run again where its reason shows, and pip is always
    "python -m pip": Scripts\\pip.exe is a launcher antivirus can take."""
    block = _engine_venv_lines()
    check = '"%ENGINEPY%" -m pip --version <nul >nul 2>&1'
    at = [i for i, ln in enumerate(block) if ln == check]
    assert len(at) == 3, at
    gate = block.index('if not "%GATE%"=="0" goto :enginevenvgone')
    assert gate < at[0] < block.index(":enginevenvrebuild")
    assert block[at[0] + 1] == 'if "%ERRORLEVEL%"=="0" goto :enginedeps'
    nopip = block[at[0] + 2:block.index(":enginevenvgone")]
    assert nopip[-1] == "goto :enginevenvrebuild" and "no pip" in nopip[0]
    made = block.index(":enginevenvmade")
    assert at[1] == made + 1
    ensure = block.index('"%ENGINEPY%" -m ensurepip --upgrade --default-pip <nul')
    assert at[1] < ensure < at[2], "ensurepip runs once more, out loud"
    # the delete is checked, so a venv held open is not built over
    rd = block.index('rd /s /q "%ENGINEVENV%" >nul 2>&1')
    assert block[rd + 1] == 'if not exist "%ENGINEPY%" goto :enginevenvmake'
    code = _code(_engine_section().split("\r\n"))
    assert not [ln for ln in code if "Scripts\\pip" in ln]
    assert not [ln for ln in code if "--upgrade pip" in ln]
    pips = [ln for ln in code if " -m pip install " in ln]
    assert len(pips) == 2 and all(
        ln.startswith('"%ENGINEPY%" -m pip install ') for ln in pips), pips


def test_the_engine_venv_folder_is_cleaned_before_it_is_used():
    """A trailing backslash on FLUBNF_ENGINE_VENV escaped the closing quote
    of every "%ENGINEVENV%" handed to venv; a stray quote broke the IFs."""
    order = [LINES.index(ln) for ln in (
        'set "ENGINEVENV=%FLUBNF_ENGINE_VENV%"',
        'if not defined ENGINEVENV set "ENGINEVENV=%USERPROFILE%\\.venvs\\flubnf-engine"',
        'set "ENGINEVENV=%ENGINEVENV:"=%"',
        'if "%ENGINEVENV:~-1%"=="\\" set "ENGINEVENV=%ENGINEVENV:~0,-1%"',
        'set "ENGINEPY=%ENGINEVENV%\\Scripts\\python.exe"')]
    assert order == sorted(order) and order[-1] - order[0] < 12, order
    # the first use is ENGINEPY's, built from the cleaned value
    assert min(i for i, ln in enumerate(LINES) if "%ENGINEVENV%" in ln
               and not ln.startswith("rem ")) == order[-1]


def test_conda_is_found_once_from_one_root():
    """CONDAPY and CONDABAT came from two lists of four folders. Anaconda in
    C:\\anaconda3 (where its installer sends a profile name with a space),
    Miniconda, Miniforge, or Anaconda reached only from Anaconda Prompt then
    read as "install Anaconda". One root now, with both python.exe and
    condabin\\conda.bat: CONDA_EXE, environments.txt, then the folders. It
    is found after :deps (lines 1-65 are frozen), before anything uses it."""
    search = _conda_search()
    code = _code(search)
    assert code[0] == 'set "CONDAROOT="'
    assert code[1].startswith(
        'if defined CONDA_EXE for %%R in ("%CONDA_EXE%\\..\\..") do ')
    assert code[2].startswith(
        'if not defined CONDAROOT if exist "%USERPROFILE%\\.conda\\environments.txt" '
        'for /f "usebackq delims=" %%E in ("%USERPROFILE%\\.conda\\environments.txt") do ')
    assert code[3].startswith("for %%R in (")
    assert re.findall(r'"([^"]+)"', code[3].split(" do ")[0]) == CONDA_FOLDERS
    for ln, var in zip(code[1:4], ("%%~fR", "%%E", "%%~R")):
        assert (f'if exist "{var}\\python.exe" if exist "{var}\\condabin\\conda.bat" '
                f'set "CONDAROOT={var}"') in ln, ln
    assert " do if not defined CONDAROOT " in code[2] + code[3]
    assert code[4:] == [
        'set "CONDAPY="', 'set "CONDABAT="',
        'if defined CONDAROOT set "CONDAPY=%CONDAROOT%\\python.exe"',
        'if defined CONDAROOT set "CONDABAT=%CONDAROOT%\\condabin\\conda.bat"']
    # set nowhere else after the frozen lines, and used only after this
    later = LINES[FROZEN_LINES:]
    assert [ln for ln in later if 'set "CONDABAT=' in ln] == code[5:8:2]
    assert [ln for ln in later if 'set "CONDAPY=' in ln] == code[4:7:2]
    found = LINES.index(code[-1])
    uses = [i for i, ln in enumerate(LINES) if not ln.startswith("rem ")
            and ("%CONDAPY%" in ln or "%CONDABAT%" in ln)]
    assert uses and min(uses) > found
    assert _label_at("deps") < found < _label_at("firstrun")


def test_conda_create_asks_for_x64_and_shows_why_it_failed():
    """On an ARM laptop some conda releases, x64 themselves, called the PC
    win-arm64 and made an ARM64 Python. CONDA_SUBDIR=win-64 is set for the
    one call; the console must not inherit it. Its output was sent to nul,
    the very text that names the cause (Terms of Service, the network); its
    input still is, so a question of its own cannot wait unanswered. The
    package asked for is the same (decision D3)."""
    block = _engine_venv_lines()
    call = block.index('call "%CONDABAT%" create -y -p "%CONDAENV%" python=3.12 <nul')
    assert block[call - 2:call + 2] == [
        "setlocal", 'set "CONDA_SUBDIR=win-64"', block[call], "endlocal"]
    assert 'set "CONDAENV=%USERPROFILE%\\.venvs\\flubnf-engine-py312"' in block
    assert sum("CONDA_SUBDIR" in ln for ln in _code(LINES)) == 1


def test_py_install_is_offered_only_where_the_install_manager_is():
    """The older py.exe takes "install" for a script to run, so `py install
    3.12` is printed only when pymanager is there, and not on an ARM PC,
    where it may pick the ARM64 build; Anaconda otherwise, or Anaconda
    Prompt for one installed where nothing looks."""
    block = _engine_venv_lines()
    offer = block.index("echo       py install 3.12")
    assert block[offer - 4:offer - 1] == [
        "if defined ARMPC goto :enginevenvarm", "where pymanager >nul 2>&1",
        "if errorlevel 1 goto :enginevenvanaconda"]
    assert sum("py install" in ln for ln in _code(LINES)) == 1
    anaconda = " ".join(_after_label("\r\n".join(block), "enginevenvanaconda",
                                     "goto :").split())
    assert "anaconda.com/download" in anaconda and "Anaconda Prompt" in anaconda
    assert 'echo "%~f0"' in anaconda
    failvenv = " ".join(_after_label(BAT, "failvenv", "pause").split())
    assert "Anaconda Prompt" in failvenv


def test_the_package_index_is_tried_before_minutes_of_pip():
    """On a network that drops PyPI's traffic, pip's retries took minutes,
    twice an open, and ended in "no matching distribution". Five seconds
    through pip first; then the size and time on screen, and pip without -q
    or a self-upgrade, so the window shows what it fetches."""
    block = _engine_venv_lines()
    index = block.index('"%ENGINEPY%" -m pip index versions numpy --retries 0 '
                        '--timeout 5 --disable-pip-version-check <nul >nul 2>&1')
    assert block[index + 1] == 'if "%ERRORLEVEL%"=="0" goto :engineindex'
    assert "pypi.org" in block[index + 2]
    told = next(i for i, ln in enumerate(block) if "about 100 MB" in ln)
    install = next(i for i, ln in enumerate(block)
                   if ln.startswith('"%ENGINEPY%" -m pip install --disable'))
    assert index < told < install
    assert "minutes" in block[told] + block[told + 1]
    assert " -q " not in block[install]


def test_the_fork_is_compiled_quietly_before_the_probe():
    """The probe is the first import of a fresh unpack, and the fork's "\\d"
    regexes printed about 25 SyntaxWarnings right above "engine ready"."""
    block = _engine_venv_lines()
    editable = next(i for i, ln in enumerate(block) if " -e \"%PYBNFDIR%\"" in ln)
    compiled = block.index(
        '"%ENGINEPY%" -W ignore -m compileall -q "%PYBNFDIR%\\pybnf" <nul >nul 2>&1')
    probe = next(i for i, ln in enumerate(block)
                 if "from pybnf.pf import ParticleFilter" in ln)
    assert editable < compiled < probe
    assert block[probe + 1] == 'if not "%ERRORLEVEL%"=="0" goto :engineprobefailed'


def test_a_failed_probe_names_a_missing_visual_cpp_runtime():
    """libroadrunner imports MSVCP140.dll and ships none, and a python.org
    Python does not bring it: the probe failed on every open with a bare
    DLL error. Keyed on the file, not on the error text."""
    failed = _after_label(BAT, "engineprobefailed", "\r\n:enginevcruntime\r\n")
    assert ('if not exist "%SystemRoot%\\System32\\msvcp140.dll" '
            "goto :enginevcruntime") in failed
    assert 'ren "%ENGINEVENV%" "%VENVLEAF%-old"' in failed
    runtime = _after_label(BAT, "enginevcruntime", "goto :")
    assert "https://aka.ms/vc14/vc_redist.x64.exe" in runtime
    assert "Visual C++ Redistributable for x64" in " ".join(runtime.split())


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
    # None takes a variable out (CONDA_EXE on a runner with conda)
    for name in [k for k, v in env.items() if v is None]:
        del env[name]
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
            "echo ARCHIVE=[%ARCHIVE%] BUNDLE=[%BUNDLE%] ENGINEOK=[%ENGINEOK%]\n"
            "echo REACHED\nexit /b 0\n\n"
            + (BAT[sub:] if stop < 0 else BAT[sub:stop + 2]))


def _version_bytes(stamp: str) -> bytes:
    """VERSION as scripts/cut_engine_archive.sh writes it: three printf
    lines, LF only (the cut runs on a Mac), the commit subject as written,
    here with a ';' in it. write_text would give CRLF on Windows, the one
    shape set /p read correctly."""
    return (f"{stamp}\n"
            "cut 2026-10-13 from https://github.com/elyfmiller/PyBNF-Private.git\n"
            "subject: pf: keep the seed; resample after the update\n"
            ).encode("ascii")


def _engine_archive(tmp_path: Path, folder: Path, stamp: str,
                    cut: float) -> Path:
    """pybnf-pf-<sha>.tar.gz in `folder`, its files dated `cut`: tar puts
    that date back on the unpacked VERSION, as it does for a real cut."""
    sha = stamp.split()[-1]
    src = tmp_path / f"cut-{sha}" / "PyBNF-Private"
    (src / "pybnf").mkdir(parents=True)
    # a regular package, as the fork is: an installed pybnf would otherwise
    # win the import over a namespace folder ahead of it on sys.path
    (src / "pybnf" / "__init__.py").write_bytes(b"")
    (src / "pybnf" / "pf.py").write_bytes(b"class ParticleFilter: pass\n")
    (src / "setup.py").write_bytes(b"from setuptools import setup; setup()\n")
    (src / "VERSION").write_bytes(_version_bytes(stamp))
    for f in (src / "pybnf" / "pf.py", src / "setup.py", src / "VERSION"):
        os.utime(f, (cut, cut))
    arc = folder / f"pybnf-pf-{sha}.tar.gz"
    with tarfile.open(arc, "w:gz") as tar:
        tar.add(src, arcname="PyBNF-Private")
    return arc


def _first_line(path: Path) -> str:
    return path.read_bytes().split(b"\n", 1)[0].decode("ascii")


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


@windows_only
@pytest.mark.parametrize("imports", [True, False],
                         ids=["new-copy-imports", "new-copy-does-not-import"])
def test_windows_the_engine_file_left_in_downloads_survives_every_later_open(
        tmp_path, imports):
    """The docs say to leave the engine file in Downloads, so every later
    open compares its stamp with the unpacked copy's. set /p read the LF-only
    VERSION whole, and the line breaks it carried into the IF that compares
    the stamps ended the launcher before the console started: the window just
    closed, on every open. Runs the search-and-unpack block as the first
    open, the second, a newer file arriving, and the open after that. The
    newer copy is probed as the one it replaced was: one that imports goes
    to the console, one that does not goes through pip and the probe."""
    home, local = tmp_path / "home", tmp_path / "local"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    local.mkdir()
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    unpacked = local / "FluBNF" / "PyBNF-Private"
    day = 24 * 3600
    now = time.time()
    lab = _engine_archive(tmp_path, downloads, "feature/particle-filter 2fdadee",
                          cut=now - 3 * day)
    os.utime(lab, (now - 2 * day, now - 2 * day))   # saved a day after the cut

    def run(pybnfdir: Path, engine_ok: bool,
            **extra: str) -> subprocess.CompletedProcess:
        env = {"USERPROFILE": str(home), "LOCALAPPDATA": str(local),
               "OneDrive": str(tmp_path / "no-onedrive"),
               "PYBNFDIR": str(pybnfdir), **extra}
        if engine_ok:
            env["ENGINEOK"] = "1"
        r = _cmd(slice_dir / "engine-file.bat", _engine_file_block(),
                 slice_dir, **env)
        assert r.returncode == 0, _said(r)
        assert "REACHED" in r.stdout, _said(r)
        for crash in ("syntax of the command", "was unexpected"):
            assert crash not in r.stdout + r.stderr, _said(r)
        return r

    def kept() -> list[Path]:
        return sorted(unpacked.parent.glob("PyBNF-Private.replaced-*"))

    # first open: nothing on disk, so PYBNFDIR is the default; it unpacks
    r = run(local / "FluBNF" / "PyBNF-pf", engine_ok=False)
    assert (unpacked / "pybnf" / "pf.py").is_file(), _said(r)
    assert (unpacked / "VERSION").read_bytes() == _version_bytes(
        "feature/particle-filter 2fdadee"), "tar changed VERSION's line ends"
    stamps = [ln for ln in r.stdout.splitlines() if "version stamp:" in ln]
    assert stamps == ["  version stamp: feature/particle-filter 2fdadee"], \
        _said(r)

    # second open: the unpacked copy is found, the stamps match, nothing moves
    r = run(unpacked, engine_ok=True)
    assert kept() == [], _said(r)
    assert "a different engine archive" not in r.stdout, _said(r)
    assert "ENGINEOK=[1]" in r.stdout, _said(r)

    # a newer build arrives beside the old file: replaced once, the old copy
    # kept, and the new one put through the import probe. The engine's
    # Python is a real exe either way: a .bat run without call never returns.
    _engine_archive(tmp_path, downloads, "feature/particle-filter 8b28edf",
                    cut=now - day)
    if imports:
        stub = tmp_path / "stub"
        stub.mkdir()
        (stub / "bngsim.py").write_bytes(b"__version__ = '0.0'\n")
        probe = {"ENGINEPY": sys.executable, "PYTHONPATH": str(stub)}
    else:
        probe = {"ENGINEPY": str(tmp_path / "no-venv" / "python.exe")}
    r = run(unpacked, engine_ok=True, **probe)
    assert len(kept()) == 1, _said(r)
    assert _first_line(unpacked / "VERSION") == \
        "feature/particle-filter 8b28edf", _said(r)
    assert _first_line(kept()[0] / "VERSION") == \
        "feature/particle-filter 2fdadee", _said(r)
    assert ("a different engine archive has arrived: on disk "
            "feature/particle-filter 2fdadee, archive "
            "feature/particle-filter 8b28edf") in r.stdout, _said(r)
    if imports:
        assert "ENGINEOK=[1]" in r.stdout, (
            "a replaced engine that imports was sent through pip, which a "
            "network without PyPI reports as no engine\n" + _said(r))
    else:
        assert "ENGINEOK=[]" in r.stdout, (
            "a replaced engine that does not import went straight to the "
            "console\n" + _said(r))

    # and the open after that leaves it alone
    r = run(unpacked, engine_ok=True)
    assert len(kept()) == 1, _said(r)
    assert "ENGINEOK=[1]" in r.stdout, _said(r)


@windows_only
def test_windows_a_pybnf_release_beside_the_lab_file_is_not_the_engine(
        tmp_path):
    """PyPI's pybnf-<version>.tar.gz and GitHub's PyBNF-<version>.tar.gz
    matched pybnf*.tar.gz, and the newest file wins: saved after the lab's
    file, either one was unpacked instead, and the student was told the lab's
    copy had not finished downloading. Only pybnf-pf-*.tar.gz counts."""
    home, local = tmp_path / "home", tmp_path / "local"
    downloads = home / "Downloads"
    downloads.mkdir(parents=True)
    local.mkdir()
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    old = time.time() - 2 * 24 * 3600
    lab = _engine_archive(tmp_path, downloads, "feature/particle-filter 2fdadee",
                          cut=old)
    os.utime(lab, (old, old))
    for top in ("pybnf-1.8.1", "PyBNF-1.2.2"):       # both saved later
        src = tmp_path / "releases" / top
        (src / "pybnf").mkdir(parents=True)
        (src / "pybnf" / "__init__.py").write_bytes(b"")
        with tarfile.open(downloads / f"{top}.tar.gz", "w:gz") as tar:
            tar.add(src, arcname=top)

    r = _cmd(slice_dir / "engine-file.bat", _engine_file_block(), slice_dir,
             USERPROFILE=str(home), LOCALAPPDATA=str(local),
             OneDrive=str(tmp_path / "no-onedrive"),
             PYBNFDIR=str(local / "FluBNF" / "PyBNF-pf"))

    assert "REACHED" in r.stdout, _said(r)
    m = re.search(r"ARCHIVE=\[([^\]]*)\]", r.stdout)
    assert m and Path(m.group(1)).name == lab.name, _said(r)
    assert "engine archives found" not in r.stdout, _said(r)
    assert (local / "FluBNF" / "PyBNF-Private" / "pybnf" / "pf.py").is_file()
    assert not (local / "FluBNF" / "pybnf-1.8.1").exists(), _said(r)
    assert not (local / "FluBNF" / "PyBNF-1.2.2").exists(), _said(r)


@windows_only
def test_windows_a_miss_names_every_folder_it_searched(tmp_path):
    """The folder list printed when no engine file turns up: this file's
    folder and the one above it come in as the argument, since %0 inside a
    called label names the label."""
    home, onedrive = tmp_path / "home", tmp_path / "onedrive"
    slice_dir = tmp_path / "slice"
    slice_dir.mkdir()
    sub = BAT.index("\r\n:enginelookedin\r\n") + 2
    stop = BAT.index("\r\n\r\n", sub)
    text = ('@echo off\nsetlocal\ncall :enginelookedin "%~dp0."\n'
            "echo REACHED\nexit /b 0\n\n" + BAT[sub:stop + 2])

    r = _cmd(slice_dir / "looked.bat", text, slice_dir,
             USERPROFILE=str(home), OneDrive=str(onedrive))

    assert "REACHED" in r.stdout, _said(r)
    shown = [Path(ln.strip()).resolve() for ln in r.stdout.splitlines()
             if ln.startswith("    ")]
    expected = [slice_dir, tmp_path] + [
        root / name for root in (home, onedrive)
        for name in ("Downloads", "Desktop", "Documents")]
    assert sorted(shown) == sorted(p.resolve() for p in expected), _said(r)


def _sync_block() -> str:
    start = BAT.index("\r\n:sync\r\n") + 2
    end = BAT.index("\r\n:data\r\n") + 2
    return ("@echo off\nsetlocal\n" + BAT[start:end]
            + ":data\necho REACHED-DATA\nexit /b 0\n"
            + ":fail\necho REACHED-FAIL\nexit /b 1\n")


@windows_only
@pytest.mark.parametrize("bng", [True, False], ids=["bng-present", "bng-missing"])
def test_windows_a_venv_without_bionetgen_is_refreshed_though_the_stamp_matches(
        tmp_path, bng):
    """A first run closed during pip's last few minutes leaves flubnf.exe
    without bionetgen, and every later open skips :firstrun. The refresh
    runs whenever BNG2.pl is missing, stamp or not, and a failed one still
    reaches the console."""
    folder = tmp_path / "flubnf"
    venv = folder / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "flubnf.exe").write_bytes(b"")
    # a real program that fails, as pip does offline
    root = os.environ.get("SystemRoot", r"C:\Windows")
    shutil.copy(Path(root) / "System32" / "where.exe",
                venv / "Scripts" / "pip.exe")
    (folder / "pyproject.toml").write_bytes(b"[project]\nname = \"flubnf\"\n")
    shutil.copy(folder / "pyproject.toml", venv / "pyproject.stamp")
    if bng:
        bng_win = venv / "Lib" / "site-packages" / "bionetgen" / "bng-win"
        bng_win.mkdir(parents=True)
        (bng_win / "BNG2.pl").write_bytes(b"")

    r = _cmd(tmp_path / "sync.bat", _sync_block(), folder)

    assert "REACHED-DATA" in r.stdout, _said(r)
    if bng:
        assert "refreshing" not in r.stdout, _said(r)
        assert "BioNetGen" not in r.stdout, _said(r)
    else:
        assert "BioNetGen (BNG2.pl) is missing" in r.stdout, _said(r)


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


# ----------------------------------------- :perlblock run with cmd.exe (Windows)
def _exe(folder: Path, name: str, body: str) -> Path:
    """`folder`\\`name`.exe, a real program that runs `body` with this
    Python, built as pip builds its console scripts (distlib's launcher,
    which exits with the code its Python exited with). winget and perl are
    programs: a .bat stand-in would not do, since FluBNF.bat runs them
    without `call`, and a batch file run that way never hands control back."""
    try:
        from pip._vendor.distlib import scripts
    except ImportError:
        scripts = pytest.importorskip("distlib.scripts")
    src = folder.parent / "shim-src" / f"{folder.name}-{name}"
    src.mkdir(parents=True, exist_ok=True)
    (src / f"{name}.py").write_text("#!python\n" + body, encoding="ascii")
    folder.mkdir(parents=True, exist_ok=True)
    maker = scripts.ScriptMaker(str(src), str(folder))
    # quoted by hand: distlib leaves an executable it is given as it is
    exe_path = sys.executable
    maker.executable = f'"{exe_path}"' if " " in exe_path else exe_path
    made = maker.make(f"{name}.py")
    exe = folder / f"{name}.exe"
    assert exe.is_file(), made
    return exe


def _perl(folder: Path, osname: str) -> Path:
    """perl.exe whose $^O is `osname` (MSWin32 for Strawberry, msys for the
    one in Git's usr\\bin), as far as the launcher's probe can tell."""
    return _exe(folder, "perl", f"""import sys
code = " ".join(sys.argv[1:])
if "q(MSWin32)" in code:
    sys.exit(0 if {osname!r} == "MSWin32" else 1)
print({osname!r})
""")


def _winget(folder: Path, calls: Path, code: int,
            leaves: Path | None = None) -> Path:
    """winget.exe that notes how it was run and exits with `code`. With
    `leaves` (a perl.exe) it first puts a copy where Strawberry's installer
    puts perl.exe, under %SystemDrive%."""
    left = str(leaves) if leaves else None
    return _exe(folder, "winget", f"""import os, shutil, sys
with open({str(calls)!r}, "a") as f:
    f.write("winget " + " ".join(sys.argv[1:]) + "\\n")
print("WINGET-RAN", flush=True)
if {left!r}:
    to = os.path.join(os.environ["SystemDrive"] + os.sep, "Strawberry",
                      "perl", "bin")
    os.makedirs(to, exist_ok=True)
    shutil.copy({left!r}, os.path.join(to, "perl.exe"))
sys.exit({code})
""")


def _choice(folder: Path, calls: Path, answer: int) -> Path:
    """choice.exe that answers at once, as a student would: 1 is Y, 2 is N."""
    key = "Y" if answer == 1 else "N"
    return _exe(folder, "choice", f"""import sys
with open({str(calls)!r}, "a") as f:
    f.write("choice " + " ".join(sys.argv[1:]) + "\\n")
print(sys.argv[-1] + {key!r})
sys.exit({answer})
""")


def _perl_pc(tmp_path: Path) -> SimpleNamespace:
    """A FluBNF folder with its .venv, a system drive with nothing on it,
    and a folder for the stand-ins, ahead of System32 on PATH. `extra`
    folders go ahead of that one."""
    pc = SimpleNamespace(folder=tmp_path / "flubnf", drive=tmp_path / "drive",
                         bin=tmp_path / "bin", calls=tmp_path / "calls.txt",
                         extra=[])
    (pc.folder / ".venv").mkdir(parents=True)
    pc.drive.mkdir()
    pc.bin.mkdir()
    pc.record = pc.folder / ".venv" / "perl-offer.txt"
    pc.strawberry = pc.drive / "Strawberry" / "perl" / "bin" / "perl.exe"
    return pc


def _perl_slice() -> str:
    """:perlblock called as the launcher calls it, then whether a Windows
    perl answers on PATH, and PATH itself."""
    sub = BAT.index("\r\n:perlblock\r\n") + 2
    return ("@echo off\nsetlocal\ncall :perlblock\n"
            'perl.exe -e "exit($^O eq q(MSWin32) ? 0 : 1)" <nul >nul 2>&1 '
            "&& echo WINDOWS-PERL-ON-PATH\n"
            "echo PATH=[%PATH%]\necho REACHED\nexit /b 0\n\n" + BAT[sub:])


def _run_perl(pc: SimpleNamespace) -> subprocess.CompletedProcess:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    path = ";".join([*map(str, pc.extra), str(pc.bin), rf"{root}\System32"])
    # SYSTEMDRIVE as os.environ spells it on Windows, so it replaces the
    # real one instead of sitting beside it
    r = _cmd(pc.folder.parent / "perl-block.bat", _perl_slice(), pc.folder,
             PATH=path, SYSTEMDRIVE=str(pc.drive))
    assert "REACHED" in r.stdout, _said(r)
    for crash in ("syntax of the command", "was unexpected"):
        assert crash not in r.stdout + r.stderr, _said(r)
    return r


def _calls(pc: SimpleNamespace) -> list[str]:
    # rstrip: a .bat stand-in logs %*, and cmd keeps the blank before a
    # trailing redirection (`... python=3.12 <nul`) in %*
    if not pc.calls.exists():
        return []
    return [c.rstrip() for c in pc.calls.read_text().splitlines()]


def _strawberry_first(pc: SimpleNamespace, r: subprocess.CompletedProcess) -> bool:
    """Strawberry's three folders lead PATH, in its installer's order."""
    path = r.stdout.split("PATH=[", 1)[1].split("]", 1)[0]
    d = f"{pc.drive}\\Strawberry"
    return path.startswith(f"{d}\\c\\bin;{d}\\perl\\site\\bin;{d}\\perl\\bin;")


@windows_only
def test_windows_cmd_passes_a_negative_exit_code_through(tmp_path):
    """What the winget fix rests on, checked on Windows itself: a program's
    negative exit code (winget's 0x8A15010C for a declined permission
    prompt) reaches %ERRORLEVEL% as that number, and `if errorlevel 1`,
    which the launcher used to trust, does not see it."""
    exe = _exe(tmp_path / "bin", "declines", "import sys\nsys.exit(-1978334964)\n")
    text = (f'@echo off\n"{exe}"\nset "WG=%ERRORLEVEL%"\necho WG=[%WG%]\n'
            "if errorlevel 1 echo IF-ERRORLEVEL-1-SAW-IT\nexit /b 0\n")

    r = _cmd(tmp_path / "code.bat", text, tmp_path)

    assert "WG=[-1978334964]" in r.stdout, _said(r)
    assert "IF-ERRORLEVEL-1-SAW-IT" not in r.stdout, _said(r)


@windows_only
def test_windows_a_windows_perl_on_path_is_all_it_takes(tmp_path):
    pc = _perl_pc(tmp_path)
    _perl(tmp_path / "Perl64" / "bin", "MSWin32")
    pc.extra.append(tmp_path / "Perl64" / "bin")
    _winget(pc.bin, pc.calls, 0)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    assert r.stdout.startswith("WINDOWS-PERL-ON-PATH"), _said(r)
    assert _calls(pc) == []
    assert not pc.record.exists()


@windows_only
@pytest.mark.parametrize("code, why, recorded", [
    (-1978334964, "declined or not answered in time", True),
    (-1978335174, "A policy on this PC blocks the install", True),
    (-1978334961, "A policy on this PC blocks the install", True),
    (-1978335224, None, True),
    (-1978334974, "Another install is running", False),
], ids=["declined", "group-policy", "installer-policy", "download-failed",
        "another-install"])
def test_windows_a_failed_winget_is_never_called_installed(tmp_path, code, why,
                                                           recorded):
    """The question defaults to Y, so a student who walked away gets
    Windows' permission prompt with nobody there; declined, it exits
    0x8A15010C. That code, and every other winget failure, is negative, and
    the launcher printed "Perl installed" for each. Now the code is named,
    the offer is recorded once, and the next open only reminds. Another
    install in progress is the exception: the next open asks again."""
    pc = _perl_pc(tmp_path)
    _winget(pc.bin, pc.calls, code)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    out = r.stdout
    assert f"winget did not install Strawberry Perl (code {code})." in out, \
        _said(r)
    if why:
        assert why in out, _said(r)
    assert "installed and ready" not in out and "Perl installed" not in out
    assert "WINDOWS-PERL-ON-PATH" not in out
    # told what to expect before winget ran
    assert out.index("Windows will ask permission") < out.index("WINGET-RAN")
    assert "flashing shield on the taskbar" in out, _said(r)
    calls = _calls(pc)
    assert [c.split()[0] for c in calls] == ["choice", "winget"], calls
    assert "--source winget" in calls[1], calls
    assert pc.record.exists() == recorded, _said(r)

    # the next open
    r = _run_perl(pc)
    again = _calls(pc)[len(calls):]
    if recorded:
        assert pc.record.read_text().strip() == f'"winget {code}"'
        assert again == [], again
        assert "https://strawberryperl.com" in r.stdout, _said(r)
    else:
        assert [c.split()[0] for c in again] == ["choice", "winget"], again


@windows_only
@pytest.mark.parametrize("code", [0, -1978334967], ids=["exit-0", "restart-due"])
def test_windows_winget_is_judged_by_the_perl_it_left(tmp_path, code):
    """Success is perl.exe where Strawberry's installer puts it, whatever
    the code (a restart still due is not a failure). Its folders go first
    on this window's PATH: the installer's PATH change reaches only windows
    opened after it, and the console starts from this one."""
    pc = _perl_pc(tmp_path)
    native = _perl(tmp_path / "stock", "MSWin32")
    _winget(pc.bin, pc.calls, code, leaves=native)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    assert "Strawberry Perl installed and ready." in r.stdout, _said(r)
    assert "did not install" not in r.stdout, _said(r)
    assert pc.strawberry.is_file()
    assert "WINDOWS-PERL-ON-PATH" in r.stdout, _said(r)
    assert _strawberry_first(pc, r), _said(r)
    assert pc.record.read_text().strip() == '"installed"'


@windows_only
def test_windows_a_unix_style_perl_on_path_does_not_count(tmp_path):
    """Git for Windows with its Unix tools on PATH brings a perl whose $^O
    is msys. `where perl` passed, so the offer never came, and BNG2.pl
    cannot run under it. It is named, and the offer is made."""
    pc = _perl_pc(tmp_path)
    git = tmp_path / "Git" / "usr" / "bin"
    _perl(git, "msys")
    pc.extra.append(git)
    _winget(pc.bin, pc.calls, 0)
    _choice(pc.bin, pc.calls, 2)

    r = _run_perl(pc)

    assert "The perl on PATH is not a Windows Perl" in r.stdout, _said(r)
    assert "Git\\usr\\bin\\perl.exe" in r.stdout, _said(r)
    assert [c.split()[0] for c in _calls(pc)] == ["choice"], _calls(pc)
    assert "skipped." in r.stdout, _said(r)
    assert pc.record.read_text().strip() == '"declined"'
    assert "https://strawberryperl.com" in r.stdout, _said(r)
    assert "WINDOWS-PERL-ON-PATH" not in r.stdout, _said(r)


@windows_only
@pytest.mark.parametrize("git_perl", [False, True],
                         ids=["no-perl-on-path", "git-perl-first"])
def test_windows_strawberry_on_disk_goes_on_path_and_nothing_is_offered(
        tmp_path, git_perl):
    """Installed, but not on this window's PATH (a Command Prompt opened
    before the install, a machine PATH cut short), or behind Git's perl:
    its folders go first and nothing is offered, so winget is not run for a
    Perl that is already here."""
    pc = _perl_pc(tmp_path)
    _perl(pc.strawberry.parent, "MSWin32")
    if git_perl:
        git = tmp_path / "Git" / "usr" / "bin"
        _perl(git, "msys")
        pc.extra.append(git)
    _winget(pc.bin, pc.calls, 0)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    assert _calls(pc) == [], _calls(pc)
    assert not pc.record.exists()
    assert "using Strawberry Perl from" in r.stdout, _said(r)
    assert "not a Windows Perl" not in r.stdout, _said(r)
    assert "WINDOWS-PERL-ON-PATH" in r.stdout, _said(r)
    assert _strawberry_first(pc, r), _said(r)


@windows_only
def test_windows_an_offer_already_made_is_only_a_reminder(tmp_path):
    pc = _perl_pc(tmp_path)
    pc.record.write_bytes(b'"declined"\r\n')
    _winget(pc.bin, pc.calls, 0)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    assert _calls(pc) == [], _calls(pc)
    said = [ln for ln in r.stdout.splitlines() if ln.startswith("  ")]
    assert len(said) == 2, _said(r)
    assert "Perl is still missing" in said[0], _said(r)
    assert "https://strawberryperl.com" in said[1], _said(r)
    assert "not an administrator" in said[1], _said(r)
    assert pc.record.read_bytes() == b'"declined"\r\n'


@windows_only
def test_windows_no_winget_names_the_link_and_asks_nothing(tmp_path):
    root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    if (root / "System32" / "winget.exe").exists():
        pytest.skip("this Windows has winget in System32, on the test's PATH")
    pc = _perl_pc(tmp_path)
    _choice(pc.bin, pc.calls, 1)

    r = _run_perl(pc)

    assert "winget is not on this PC" in r.stdout, _said(r)
    assert "https://strawberryperl.com" in r.stdout, _said(r)
    assert _calls(pc) == [], _calls(pc)
    assert pc.record.read_text().strip() == '"no winget"'


# ------------------------------ the engine venv block run with cmd.exe (Windows)
# A stand-in python.exe: what it is (version, platform) and how its steps go
# are in fakepy.json beside it. The launcher's own ENGINEGATE runs for real,
# with the version and platform swapped in.
FAKE_PY = """import json, os, shutil, sys
me = os.path.abspath(sys.argv[0])
here = os.path.dirname(me)
conf = os.path.join(here, "fakepy.json")
with open(conf) as f:
    cfg = json.load(f)
args = sys.argv[1:]
with open(cfg["calls"], "a") as f:
    f.write(cfg["name"] + " " + " ".join(args) + "\\n")
if not cfg.get("starts", True):
    # a venv whose base Python is gone
    sys.stderr.write("No Python at '" + here + "'\\n")
    sys.exit(103)
if args[:1] == ["-c"] and "sysconfig" in args[1]:
    import sysconfig
    sys.version_info = tuple(cfg["version"])
    sysconfig.get_platform = lambda: cfg["platform"]
    sys.argv = ["-c"] + args[2:]
    exec(args[1])
    sys.exit(98)
if args[:1] == ["-c"]:
    if cfg.get("probe", 0):
        sys.stderr.write("ImportError: DLL load failed while importing _roadrunner\\n")
        sys.exit(1)
    print("  PF engine ready, bngsim 0.15.1 -- engine ready")
    sys.exit(0)
if args[:2] == ["-m", "venv"]:
    scripts = os.path.join(args[2], "Scripts")
    os.makedirs(scripts, exist_ok=True)
    shutil.copy(me, os.path.join(scripts, "python.exe"))
    made = {k: v for k, v in cfg.items() if k != "venv"}
    made.update(cfg.get("venv", {}))
    made["name"] = "venv"
    with open(os.path.join(scripts, "fakepy.json"), "w") as f:
        json.dump(made, f)
    sys.exit(0)
if args[:3] == ["-m", "pip", "--version"]:
    if cfg.get("pip", True):
        print("pip 24.0")
        sys.exit(0)
    sys.stderr.write("No module named pip\\n")
    sys.exit(1)
if args[:3] == ["-m", "pip", "index"]:
    sys.exit(cfg.get("index", 0))
if args[:3] == ["-m", "pip", "install"]:
    sys.exit(cfg.get("install", 0))
if args[:2] == ["-m", "ensurepip"]:
    if not cfg.get("ensurepip", True):
        sys.stderr.write("ensurepip: [WinError 5] Access is denied\\n")
        sys.exit(1)
    cfg["pip"] = True
    with open(conf, "w") as f:
        json.dump(cfg, f)
    sys.exit(0)
if args[:4] == ["-W", "ignore", "-m", "compileall"]:
    sys.exit(0)
sys.stderr.write("stand-in python: not expected: " + " ".join(args) + "\\n")
sys.exit(99)
"""

# The py launcher: `py -3.12 ...` hands the rest of the line to the
# python.exe py.json names for -3.12; a version it lacks ends as py.exe's
# does, exit 103.
FAKE_PY_LAUNCHER = """import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(sys.argv[0]))
with open(os.path.join(here, "py.json")) as f:
    cfg = json.load(f)
args = sys.argv[1:]
with open(cfg["calls"], "a") as f:
    f.write("py " + " ".join(args) + "\\n")
target = cfg["versions"].get(args[0] if args else "")
if not target:
    sys.stderr.write("No suitable Python runtime found\\n")
    sys.exit(103)
sys.exit(subprocess.run([target] + args[1:]).returncode)
"""


def _python(folder: Path, calls: Path, name: str, version=(3, 12, 10),
            platform: str = "win-amd64", **acts) -> Path:
    """folder\\python.exe standing in for a Python `version` built for
    `platform`, its calls noted in `calls` under `name`. `acts` says how
    its steps go: starts, pip, index, install, ensurepip, probe, and
    `venv`, what a venv it makes does differently."""
    exe = _exe(folder, "python", FAKE_PY)
    cfg = {"name": name, "calls": str(calls), "version": list(version),
           "platform": platform, **acts}
    (folder / "fakepy.json").write_text(json.dumps(cfg), encoding="ascii")
    return exe


def _py(folder: Path, calls: Path, versions: dict) -> Path:
    exe = _exe(folder, "py", FAKE_PY_LAUNCHER)
    cfg = {"calls": str(calls), "versions": {k: str(v) for k, v in versions.items()}}
    (folder / "py.json").write_text(json.dumps(cfg), encoding="ascii")
    return exe


def _anaconda(root: Path, calls: Path, name: str, base=(3, 14, 0),
              makes: Path | None = None) -> Path:
    """root as an Anaconda install: python.exe, its base Python, and
    condabin\\conda.bat, which notes CONDA_SUBDIR and its arguments and,
    given `makes` (a folder with a stand-in python.exe), puts that Python
    where -p says, as conda create would. Without it, conda's error."""
    _python(root, calls, name, version=base)
    (root / "condabin").mkdir(exist_ok=True)
    lines = ["@echo off",
             f'>>"{calls}" echo conda CONDA_SUBDIR=[%CONDA_SUBDIR%] %*']
    if makes:
        lines += ['if not exist "%~4" mkdir "%~4"',
                  f'copy /y "{makes}\\python.exe" "%~4\\python.exe" >nul',
                  f'copy /y "{makes}\\fakepy.json" "%~4\\fakepy.json" >nul']
    else:
        lines += ["echo CondaHTTPError: HTTP 000 CONNECTION FAILED"]
    (root / "condabin" / "conda.bat").write_bytes(
        "\r\n".join(lines + [""]).encode("ascii"))
    return root


def _engine_venv_slice() -> str:
    """The conda search after :gitchecked, the engine venv's folder from
    :engineupdated, and :enginevenv to the end of the probe's failure
    text, run as FluBNF.bat runs them; the labels they end at stand in
    for the console."""
    found = BAT.index("\r\n:gitchecked\r\n") + len("\r\n:gitchecked\r\n")
    first = BAT.index('if not exist ".venv\\Scripts\\flubnf.exe" goto :firstrun')
    updated = BAT.index("\r\n:engineupdated\r\n") + 2
    probed = BAT.index("\r\nrem Installed? Cheap file tests first") + 2
    start = BAT.index("\r\n:enginevenv\r\n") + 2
    end = BAT.index("\r\n:enginebadbundle\r\n") + 2
    return ("@echo off\nsetlocal\n" + BAT[found:first] + BAT[updated:probed]
            + "goto :enginevenv\n" + BAT[start:end]
            + ":enginefailed\necho REACHED-FAILED\nexit /b 1\n"
            + ":startconsole\necho REACHED-CONSOLE CONDA_SUBDIR=[%CONDA_SUBDIR%]"
            + " ENGINE=[%FLUBNF_PY_ENGINE%]\nexit /b 0\n"
            + ":recordengine\ngoto :eof\n")


def _engine_pc(tmp_path: Path) -> SimpleNamespace:
    """A PC with no Python and no Anaconda: a profile, ProgramData and a
    system drive of its own, a folder for stand-ins ahead of System32 on
    PATH (`extra` folders go ahead of that), and the engine unpacked."""
    pc = SimpleNamespace(folder=tmp_path / "flubnf", home=tmp_path / "home",
                         bin=tmp_path / "bin", data=tmp_path / "programdata",
                         drive=tmp_path / "drive", calls=tmp_path / "calls.txt",
                         pybnf=tmp_path / "PyBNF-Private", extra=[])
    for d in (pc.folder / ".venv", pc.home, pc.bin, pc.data, pc.drive):
        d.mkdir(parents=True)
    (pc.pybnf / "pybnf").mkdir(parents=True)
    (pc.pybnf / "pybnf" / "pf.py").write_bytes(b"class ParticleFilter: pass\n")
    pc.venv = pc.home / ".venvs" / "flubnf-engine"
    pc.condaenv = pc.home / ".venvs" / "flubnf-engine-py312"
    return pc


def _run_engine_venv(pc: SimpleNamespace, **env) -> subprocess.CompletedProcess:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    settings = {
        "PATH": ";".join([*map(str, pc.extra), str(pc.bin), rf"{root}\System32"]),
        "USERPROFILE": str(pc.home),
        "LOCALAPPDATA": str(pc.home / "AppData" / "Local"),
        "PROGRAMDATA": str(pc.data), "SYSTEMDRIVE": str(pc.drive),
        "PYBNFDIR": str(pc.pybnf),
        "ATTEMPT": str(pc.folder / ".venv" / "engine-attempt.txt"),
        "PROCESSOR_ARCHITECTURE": "AMD64", "PROCESSOR_ARCHITEW6432": None,
        "CONDA_EXE": None, "CONDA_SUBDIR": None, "FLUBNF_ENGINE_VENV": None,
        **env}
    r = _cmd(pc.folder.parent / "engine-venv.bat", _engine_venv_slice(),
             pc.folder, **settings)
    assert "REACHED-" in r.stdout, _said(r)
    for crash in ("syntax of the command", "was unexpected",
                  "cannot find the batch label"):
        assert crash not in r.stdout + r.stderr, _said(r)
    return r


def _assert_installed(pc: SimpleNamespace, r: subprocess.CompletedProcess) -> None:
    """The engine venv's steps after its gate, in order: pip there, the
    index reachable, the packages with pip's output showing, the fork,
    compiled, then probed. Its calls are noted as "venv"."""
    assert "REACHED-CONSOLE" in r.stdout, _said(r)
    assert (pc.venv / "Scripts" / "python.exe").is_file(), _said(r)
    steps = [c for c in _calls(pc) if c.startswith("venv ")
             and "sysconfig" not in c]
    wanted = ["venv -m pip --version",
              ("venv -m pip index versions numpy --retries 0 --timeout 5 "
               "--disable-pip-version-check"),
              "venv -m pip install --disable-pip-version-check numpy<2 scipy",
              (f"venv -m pip install -q --disable-pip-version-check -e "
               f"{pc.pybnf} --no-deps"),
              f"venv -W ignore -m compileall -q {pc.pybnf}\\pybnf",
              "venv -c import sys; sys.path.insert(0, sys.argv[1]); import bngsim"]
    assert len(steps) == len(wanted), steps
    for step, want in zip(steps, wanted):
        assert step.startswith(want), (step, want)
    out = r.stdout
    assert out.index("about 100 MB") < out.index("PF engine ready"), _said(r)


@windows_only
def test_windows_no_python_at_all_says_so_and_names_anaconda(tmp_path):
    """No py, no python, no Anaconda: the window said "Engine setup did not
    finish (see above)" with nothing above it, on every open."""
    pc = _engine_pc(tmp_path)

    r = _run_engine_venv(pc)

    out = r.stdout
    assert "REACHED-FAILED" in out, _said(r)
    for said in ("py, the Python launcher: not installed", "python: not on PATH",
                 "Anaconda: not found", "No Python on this PC can run the engine",
                 "install Anaconda (anaconda.com/download", "Anaconda Prompt"):
        assert said in out, _said(r)
    assert "py install" not in out, _said(r)
    assert not pc.venv.exists()
    assert _calls(pc) == []


@windows_only
@pytest.mark.parametrize("pymanager, arch, step", [
    (False, "AMD64", "anaconda"), (True, "AMD64", "py install"),
    (True, "ARM64", "anaconda")], ids=["older-py", "install-manager", "arm-pc"])
def test_windows_a_py_with_no_3_12_or_3_11(tmp_path, pymanager, arch, step):
    """py with only a newer Python: both tries went to nul, so this was
    silent too. `py install 3.12` only where the install manager is (the
    older py.exe runs "install" as a script), and not on an ARM PC."""
    pc = _engine_pc(tmp_path)
    _py(pc.bin, pc.calls, {})
    if pymanager:
        _exe(pc.bin, "pymanager", "import sys\nsys.exit(0)\n")

    r = _run_engine_venv(pc, PROCESSOR_ARCHITECTURE=arch)

    out = r.stdout
    assert "REACHED-FAILED" in out, _said(r)
    assert "py -3.12: not installed" in out, _said(r)
    assert "py -3.11: not installed" in out, _said(r)
    assert [c.split()[:2] for c in _calls(pc)] == [["py", "-3.12"], ["py", "-3.11"]]
    assert ("py install 3.12" in out) == (step == "py install"), _said(r)
    assert ("anaconda.com/download" in out) == (step == "anaconda"), _said(r)
    assert ("ARM processor" in out) == (arch == "ARM64"), _said(r)


@windows_only
def test_windows_an_arm64_3_12_is_passed_over_for_an_x64_3_11(tmp_path):
    """numpy<2, bngsim and libroadrunner have no Windows ARM64 wheel: a
    3.12 built for ARM64 passed the version check, and pip ended in a
    compiler error on every open."""
    pc = _engine_pc(tmp_path)
    arm = _python(tmp_path / "Python312-arm64", pc.calls, "py312-arm64",
                  platform="win-arm64")
    x64 = _python(tmp_path / "Python311", pc.calls, "py311", version=(3, 11, 9))
    _py(pc.bin, pc.calls, {"-3.12": arm, "-3.11": x64})

    r = _run_engine_venv(pc)

    out = r.stdout
    assert ("py -3.12: Python 3.12.10 (win-arm64), not the x64 build the "
            "engine needs") in out, _said(r)
    assert "py -3.11: Python 3.11.9 (win-amd64)" in out, _said(r)
    assert f"py311 -m venv {pc.venv}" in _calls(pc), _calls(pc)
    assert not [c for c in _calls(pc) if c.startswith("py312-arm64 -m")]
    _assert_installed(pc, r)


@windows_only
@pytest.mark.parametrize("creates", [True, False], ids=["created", "conda-failed"])
def test_windows_anaconda_makes_an_x64_3_12_for_the_engine(tmp_path, creates):
    """Anaconda's own Python is newer than the engine takes, so conda makes
    a 3.12, asked for as x64 (CONDA_SUBDIR=win-64, for that call only), and
    conda's output stays on screen: when it fails, it names the cause."""
    pc = _engine_pc(tmp_path)
    made = None
    if creates:
        made = tmp_path / "conda-made"
        _python(made, pc.calls, "conda-env")
    _anaconda(pc.home / "anaconda3", pc.calls, "anaconda", makes=made)

    r = _run_engine_venv(pc)

    out = r.stdout
    assert (f"Anaconda at {pc.home}\\anaconda3: Python 3.14.0 (win-amd64), "
            "the engine needs 3.12 or 3.11") in out, _said(r)
    conda = [c for c in _calls(pc) if c.startswith("conda ")]
    assert len(conda) == 1, conda
    assert conda[0].startswith("conda CONDA_SUBDIR=[win-64] create -y -p "), conda
    assert str(pc.condaenv) in conda[0] and conda[0].endswith("python=3.12")
    if creates:
        assert "conda's new Python: Python 3.12.10 (win-amd64)" in out, _said(r)
        assert f"conda-env -m venv {pc.venv}" in _calls(pc), _calls(pc)
        _assert_installed(pc, r)
        assert "REACHED-CONSOLE CONDA_SUBDIR=[]" in out, (
            "CONDA_SUBDIR reached the console\n" + _said(r))
    else:
        assert "REACHED-FAILED" in out, _said(r)
        assert "CondaHTTPError" in out, _said(r)
        assert "conda did not make a Python the engine can use" in out, _said(r)
        assert not pc.venv.exists()


@windows_only
def test_windows_conda_exe_names_an_anaconda_the_folders_miss(tmp_path):
    """Anaconda Prompt sets CONDA_EXE, so FluBNF.bat run from there finds
    an Anaconda wherever it went, ahead of one in the usual folders."""
    pc = _engine_pc(tmp_path)
    elsewhere = tmp_path / "Tools" / "Anaconda"
    _anaconda(elsewhere, pc.calls, "elsewhere", base=(3, 12, 10))
    _anaconda(pc.home / "anaconda3", pc.calls, "home-anaconda", base=(3, 12, 10))

    r = _run_engine_venv(pc, CONDA_EXE=str(elsewhere / "Scripts" / "conda.exe"))

    calls = _calls(pc)
    assert f"elsewhere -m venv {pc.venv}" in calls, calls
    assert not [c for c in calls if c.startswith(("home-anaconda ", "conda "))]
    _assert_installed(pc, r)


def _conda_root(root: Path, condabin: bool = True) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "python.exe").write_bytes(b"")
    if condabin:
        (root / "condabin").mkdir(exist_ok=True)
        (root / "condabin" / "conda.bat").write_bytes(b"")
    return root


@windows_only
@pytest.mark.parametrize("case", [
    "conda-exe", "stale-conda-exe", "environments-txt",
    "programdata-miniconda", "system-drive-anaconda", "python-only"])
def test_windows_one_conda_root_is_found_in_the_launchers_order(tmp_path, case):
    """Names and files only, nothing runs: CONDA_EXE first, then
    environments.txt, then the usual folders, and a folder counts only with
    both python.exe and condabin\\conda.bat (a conda env has the first)."""
    home, data, drive = (tmp_path / n for n in ("home", "programdata", "drive"))
    for d in (home, data, drive):
        d.mkdir()
    env = {"USERPROFILE": str(home), "LOCALAPPDATA": str(home / "AppData" / "Local"),
           "PROGRAMDATA": str(data), "SYSTEMDRIVE": str(drive), "CONDA_EXE": None}
    want = None
    if case == "conda-exe":
        want = _conda_root(tmp_path / "Tools" / "Anaconda")
        _conda_root(home / "anaconda3")
        env["CONDA_EXE"] = str(want / "Scripts" / "conda.exe")
    elif case == "stale-conda-exe":
        env["CONDA_EXE"] = str(tmp_path / "gone" / "Scripts" / "conda.exe")
        want = _conda_root(home / "anaconda3")
    elif case == "environments-txt":
        work = _conda_root(tmp_path / "envs" / "work", condabin=False)
        want = _conda_root(tmp_path / "D" / "conda")
        _conda_root(home / "miniforge3")
        (home / ".conda").mkdir()
        (home / ".conda" / "environments.txt").write_bytes(
            f"{work}\r\n{want}\r\n".encode("ascii"))
    elif case == "programdata-miniconda":
        want = _conda_root(data / "miniconda3")
    elif case == "system-drive-anaconda":
        want = _conda_root(drive / "anaconda")
    else:
        _conda_root(home / "anaconda3", condabin=False)
    start = BAT.index("\r\n:gitchecked\r\n") + len("\r\n:gitchecked\r\n")
    end = BAT.index('if not exist ".venv\\Scripts\\flubnf.exe" goto :firstrun')
    text = ("@echo off\nsetlocal\n" + BAT[start:end]
            + "echo CONDAPY=[%CONDAPY%]\necho CONDABAT=[%CONDABAT%]\nexit /b 0\n")

    r = _cmd(tmp_path / "conda-search.bat", text, tmp_path, **env)

    py = re.search(r"CONDAPY=\[([^\]]*)\]", r.stdout)
    bat = re.search(r"CONDABAT=\[([^\]]*)\]", r.stdout)
    assert py and bat, _said(r)
    if want is None:
        assert (py.group(1), bat.group(1)) == ("", ""), _said(r)
    else:
        assert Path(py.group(1)).resolve() == (want / "python.exe").resolve(), _said(r)
        assert Path(bat.group(1)).resolve() == (
            want / "condabin" / "conda.bat").resolve(), _said(r)


@windows_only
@pytest.mark.parametrize("tail", ["\\", '"'], ids=["trailing-backslash", "stray-quote"])
def test_windows_flubnf_engine_venv_is_cleaned_before_venv_sees_it(tmp_path, tail):
    """A trailing backslash reached venv as ...\\engine" and the venv was
    never made; a stray quote, which setx in Command Prompt stores for a
    quoted path ending in a backslash, broke the IFs."""
    pc = _engine_pc(tmp_path)
    _py(pc.bin, pc.calls, {"-3.12": _python(tmp_path / "Python312", pc.calls, "py312")})
    pc.venv = tmp_path / "venvs" / "engine"

    r = _run_engine_venv(pc, FLUBNF_ENGINE_VENV=str(pc.venv) + tail)

    assert f"py312 -m venv {pc.venv}" in _calls(pc), _calls(pc)
    assert f"ENGINE=[{pc.venv}\\Scripts\\python.exe]" in r.stdout, _said(r)
    _assert_installed(pc, r)


@windows_only
@pytest.mark.parametrize("case, said", [
    ("fine", "the engine venv: Python 3.12.10 (win-amd64)\n"),
    ("too-new", ("the engine venv: Python 3.14.0 (win-amd64), the engine "
                 "needs 3.12 or 3.11")),
    ("arm64", "the engine venv: Python 3.12.10 (win-arm64), not the x64 build"),
    ("gone", "the engine venv's Python does not start"),
    ("no-pip", "the engine venv has no pip"),
])
def test_windows_an_existing_engine_venv_is_kept_or_rebuilt_for_its_reason(
        tmp_path, case, said):
    """An existing venv goes through the same gate, then a pip check. A
    venv whose base Python is gone was called too new; one with no pip
    failed every open at "No module named pip" and was never rebuilt."""
    pc = _engine_pc(tmp_path)
    acts = {"fine": {}, "too-new": {"version": (3, 14, 0)},
            "arm64": {"platform": "win-arm64"}, "gone": {"starts": False},
            "no-pip": {"pip": False}}[case]
    # kept, it is the engine venv; rebuilt, the new one is
    _python(pc.venv / "Scripts", pc.calls,
            "venv" if case == "fine" else "old-venv", **acts)
    _py(pc.bin, pc.calls, {"-3.12": _python(tmp_path / "Python312", pc.calls, "py312")})

    r = _run_engine_venv(pc)

    out = r.stdout.replace("\r\n", "\n")
    assert said in out, _said(r)
    assert "too new" not in out, _said(r)
    rebuilt = f"py312 -m venv {pc.venv}" in _calls(pc)
    assert rebuilt == (case != "fine"), _calls(pc)
    assert (f'rebuilding the engine venv: "{pc.venv}"' in out) == rebuilt, _said(r)
    _assert_installed(pc, r)


@windows_only
def test_windows_an_unreachable_package_index_is_said_in_seconds(tmp_path):
    """On a network that drops PyPI's traffic pip's retries took minutes,
    twice an open, then said "no matching distribution". The five-second
    look says "network", and nothing is installed."""
    pc = _engine_pc(tmp_path)
    _python(pc.venv / "Scripts", pc.calls, "venv", index=1)

    r = _run_engine_venv(pc)

    out = r.stdout
    assert "REACHED-FAILED" in out, _said(r)
    assert "does not reach the Python package index (pypi.org)" in out, _said(r)
    calls = _calls(pc)
    assert any(c.startswith("venv -m pip index versions numpy --retries 0 "
                            "--timeout 5") for c in calls), calls
    assert not [c for c in calls if " -m pip install " in c], calls
    assert "about 100 MB" not in out, _said(r)


@windows_only
@pytest.mark.parametrize("ensurepip", [True, False],
                         ids=["ensurepip-mends-it", "ensurepip-fails"])
def test_windows_a_new_venv_without_pip_says_why(tmp_path, ensurepip):
    """venv runs ensurepip, and when that fails (antivirus, a full disk)
    the venv has python.exe and no pip. It is run once more where its
    reason shows; if pip is still missing, that is the cause on screen."""
    pc = _engine_pc(tmp_path)
    base = _python(tmp_path / "Python312", pc.calls, "py312",
                   venv={"pip": False, "ensurepip": ensurepip})
    _py(pc.bin, pc.calls, {"-3.12": base})

    r = _run_engine_venv(pc)

    out = r.stdout
    calls = _calls(pc)
    assert "venv -m ensurepip --upgrade --default-pip" in calls, calls
    assert "asking Python for it once more" in out, _said(r)
    if ensurepip:
        assert "REACHED-CONSOLE" in out, _said(r)
    else:
        assert "REACHED-FAILED" in out, _said(r)
        assert "pip would not go into the engine venv" in out, _said(r)
        assert not [c for c in calls if " -m pip index " in c], calls


@windows_only
def test_windows_a_probe_that_fails_gives_a_next_step(tmp_path):
    pc = _engine_pc(tmp_path)
    _python(pc.venv / "Scripts", pc.calls, "venv", probe=1)

    r = _run_engine_venv(pc)

    out = r.stdout
    assert "REACHED-FAILED" in out, _said(r)
    assert "but the engine does not load" in out, _said(r)
    runtime = Path(os.environ.get("SystemRoot", r"C:\Windows"),
                   "System32", "msvcp140.dll")
    if runtime.is_file():
        assert f'ren "{pc.venv}" "flubnf-engine-old"' in out, _said(r)
    else:
        assert "https://aka.ms/vc14/vc_redist.x64.exe" in out, _said(r)


@windows_only
@pytest.mark.parametrize("runtime", [True, False],
                         ids=["runtime-present", "runtime-missing"])
def test_windows_a_missing_visual_cpp_runtime_is_named(tmp_path, runtime):
    """libroadrunner imports MSVCP140.dll and ships none, and python.org's
    Python does not bring it. Only cmd's own commands run here, so
    SystemRoot can point at a Windows folder made for the test."""
    windows = tmp_path / "Windows"
    (windows / "System32").mkdir(parents=True)
    if runtime:
        (windows / "System32" / "msvcp140.dll").write_bytes(b"")
    venv = tmp_path / ".venvs" / "flubnf-engine"
    start = BAT.index("\r\n:engineprobefailed\r\n") + 2
    end = BAT.index("\r\n:enginebadbundle\r\n") + 2
    text = ("@echo off\nsetlocal\ngoto :engineprobefailed\n" + BAT[start:end]
            + ":enginefailed\necho REACHED-FAILED\nexit /b 1\n")

    r = _cmd(tmp_path / "probe-failed.bat", text, tmp_path,
             SYSTEMROOT=str(windows), ENGINEVENV=str(venv))

    out = r.stdout
    assert "REACHED-FAILED" in out, _said(r)
    assert ("https://aka.ms/vc14/vc_redist.x64.exe" in out) == (not runtime), _said(r)
    assert (f'ren "{venv}" "flubnf-engine-old"' in out) == runtime, _said(r)
