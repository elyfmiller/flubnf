"""FluBNF.bat and setup.ps1 after the engine cutover review (docs/WINDOWS.md,
docs/ENGINE.md): the public engine is the default, and the private engine,
the lab's fork, is the fallback that runs only where this copy records it.

Pinned here:

- FluBNF.bat reads FLUBNF_ENGINE as flubnf/settings.py and setup.ps1 read
  it: quotes dropped, the spaces around it trimmed, any case. So
  `set FLUBNF_ENGINE=private && FluBNF.bat` takes the private route, as the
  console it starts does;
- PUBLICROUTE, which only the public route sets, is cleared before the
  route is chosen, and a FLUBNF_PY_ENGINE_PUBLIC set with quotes no longer
  makes :recordpublic an IF syntax error;
- after a failed public install the launcher says which of three states
  the private engine is in (installed; its folder here with no venv; not
  here) and prints the switch as the whole command, which runs as typed in
  Command Prompt or PowerShell; the private route's failures print the way
  back the same way;
- setup.ps1 -Engine records the choice before anything is installed, so a
  run that stops early (no Python, pip with no network) still switches;
  -Engine private on a PC whose private engine loads stops there, with no
  pip; the record is read in every form cmd runs, and written back in the
  one FluBNF.bat and the docs name.

No cmd.exe or PowerShell runs on macOS or Linux: there the two files are
read as text, and setup.ps1's record pattern runs under Python's re. On
Windows (CI's test-windows) the blocks run with cmd.exe and setup.ps1 with
Windows PowerShell, in folders of the test's own, with stand-in programs:
nothing is installed and no network is used.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from flubnf import settings
from tests.test_windows_launcher import _cmd, _exe, _public_pc, _run_public

REPO = Path(__file__).resolve().parents[1]
# The CRLF form users run (.gitattributes), whatever this checkout has.
BAT = (REPO / "FluBNF.bat").read_bytes().replace(b"\r\n", b"\n").decode("ascii")
LINES = BAT.split("\n")
PS1 = (REPO / "setup.ps1").read_text(encoding="ascii").replace("\r\n", "\n")

windows_only = pytest.mark.skipif(
    os.name != "nt", reason="runs FluBNF.bat with cmd.exe, setup.ps1 with PowerShell")

FULL = ('powershell -NoProfile -ExecutionPolicy Bypass -File '
        '"%~dp0setup.ps1" -Engine {}')
READY_LINE = ("The private engine is installed on this PC: to run it instead "
              "(the fallback), run setup.ps1 -Engine private, then open FluBNF "
              "again.")
FORK_LINE = ("The private engine, the fallback, is on this PC but not "
             "installed yet: run setup.ps1 -Engine private, then open FluBNF "
             "again, which installs it from the engine folder here (no file "
             "needed).")
NOT_READY_LINE = ("The private engine, the fallback, needs the lab's engine "
                  "file: run setup.ps1 -Engine private, then open FluBNF with "
                  "the file in Downloads.")
BACK_LINE = ("This copy is set to the private engine (the fallback); "
             "setup.ps1 -Engine public goes back to the default, which needs "
             "no file.")
TRIM = ('for /f "tokens=1*" %%A in ("%ENGINEROUTE%") do if not "%%A"=="" '
        'if "%%B"=="" set "ENGINEROUTE=%%A"')
BLANK = 'if "%ENGINEROUTE: =%"=="" set "ENGINEROUTE=public"'


def _code(lines: list[str]) -> list[str]:
    return [ln for ln in lines if ln.strip() and not ln.startswith("rem ")]


def _after_label(name: str, until: str = "goto :") -> list[str]:
    """FluBNF.bat's code lines after `:name`, up to the first `until`."""
    m = re.search(rf"^:{name}$", BAT, re.MULTILINE)
    assert m, f"FluBNF.bat has no :{name} label"
    return _code(BAT[m.end():].split(until, 1)[0].splitlines())


def _ps1_block(start: str, end: str) -> str:
    i = PS1.index(start)
    return PS1[i:PS1.index(end, i)]


# ------------------------------------------- FluBNF.bat, read as text
def test_the_route_drops_quotes_and_the_spaces_around_the_word():
    """cmd keeps the space in `set FLUBNF_ENGINE=private && FluBNF.bat`;
    settings.py and setup.ps1 trim it. The trim comes after the quotes go
    and before the value is compared or said."""
    i = LINES.index('set "ENGINEROUTE=%ENGINEROUTE:"=%"')
    assert LINES[i + 1:i + 4] == [
        'if not defined ENGINEROUTE set "ENGINEROUTE=public"', TRIM, BLANK]
    assert LINES[i + 4].startswith(
        'if /I not "%ENGINEROUTE%"=="private" if /I not "%ENGINEROUTE%"=="public" echo ')
    assert LINES[i + 5] == 'if /I not "%ENGINEROUTE%"=="private" goto :publicengine'
    # FLUBNF_ENGINE is read in that one place
    assert [ln for ln in _code(LINES) if "%FLUBNF_ENGINE%" in ln] == [
        'if defined FLUBNF_ENGINE set "ENGINEROUTE=%FLUBNF_ENGINE%"']


def test_publicroute_is_cleared_before_the_route_is_chosen():
    """Only :publicengine sets it, to send the public install through the
    private engine's venv code; one left in the shell sent the private
    install into the 3.12-only gate and the public pip step."""
    code = _code(LINES)
    clear = code.index('set "PUBLICROUTE="')
    assert code.index(":engineupdated") < clear < code.index('set "ENGINEROUTE=public"')
    first_use = next(k for k, ln in enumerate(code) if "if defined PUBLICROUTE" in ln)
    assert clear < first_use
    assert [ln for ln in code if ln.startswith('set "PUBLICROUTE=')] == [
        'set "PUBLICROUTE="', 'set "PUBLICROUTE=1"']


def test_a_quoted_public_record_loses_its_quotes_before_it_is_compared():
    code = _code(LINES)
    i = code.index('set "PUBLICREC=%FLUBNF_PY_ENGINE_PUBLIC%"')
    assert code[i + 1] == 'if defined PUBLICREC set "PUBLICREC=%PUBLICREC:"=%"'
    assert code.index(code[i + 1]) < code.index(
        'if /I "%PUBLICREC%"=="%PUBLICPY%" goto :eof')


def test_a_public_failure_says_what_the_fallback_needs_and_the_whole_command():
    """Three states, each its own line: installed (switch, then open);
    its folder here with no venv (the private route installs it from
    there, no file); nothing here (the lab's file). Then the command that
    runs as typed: setup.ps1 by itself opens in an editor from Command
    Prompt and is refused by PowerShell."""
    probe = _code(LINES[LINES.index(":publicengine"):])
    i = probe.index('set "PRIVATEREADY="')
    assert probe[i:i + 4] == [
        'set "PRIVATEREADY="',
        'if exist "%PRIVATEPY%" if exist "%PYBNFDIR%\\pybnf\\pf.py" set "PRIVATEREADY=1"',
        'set "PRIVATEFORK="',
        'if exist "%PYBNFDIR%\\pybnf\\pf.py" set "PRIVATEFORK=1"']
    for label, first in (
            ("publicnolock", "The public engine, the default, cannot be "
             "installed: its lock file cannot be used yet (the reason is "
             "above). The console starts without it."),
            ("publicfailed", "The public engine did not install (see above). "
             "The console starts without it, and the next open tries "
             "again.")):
        assert _after_label(label) == [
            f"echo   {first}",
            f"if defined PRIVATEREADY echo   {READY_LINE}",
            f"if not defined PRIVATEREADY if defined PRIVATEFORK echo   {FORK_LINE}",
            f"if not defined PRIVATEFORK echo   {NOT_READY_LINE}",
            "echo   To switch, type this in Command Prompt or PowerShell:",
            "echo     " + FULL.format("private")], label


def test_the_private_routes_failures_print_the_way_back_in_full():
    back = ["echo   " + BACK_LINE,
            "echo   To go back, type this in Command Prompt or PowerShell:",
            "echo     " + FULL.format("public")]
    code = _code(LINES)
    at = [k for k, ln in enumerate(code) if ln == back[0]]
    assert len(at) == 3, at
    for k in at:
        assert code[k:k + 3] == back, code[k:k + 3]
    for label in ("enginefailed", "engineskipped"):
        assert back[2] in _after_label(label, "goto :startconsole"), label


def test_every_command_the_launcher_prints_names_this_folder_and_a_route():
    said = [ln for ln in LINES if "powershell " in ln and "setup.ps1" in ln
            and ln.lstrip().startswith("echo")]
    for ln in said:
        assert '-File "%~dp0setup.ps1"' in ln, ln
    assert sum(ln.endswith(FULL.format("private")) for ln in said) == 2
    assert sum(ln.endswith(FULL.format("public")) for ln in said) == 3


# --------------------------------------------- setup.ps1, read as text
def test_setup_takes_engine_in_lower_case():
    head = PS1[:PS1.index("function Say")]
    param = head.index('[ValidateSet("private", "public")][string]$Engine = "")')
    low = head.index("if ($Engine) { $Engine = $Engine.ToLowerInvariant() }")
    assert param < low


def test_engine_is_recorded_before_anything_is_installed():
    """Finding 1: the record was written about 740 lines after pip, so an
    offline -Engine private recorded nothing and the next open was public
    again. Now it is written as soon as the route is known, with the
    account's value that names the other engine cleared beside it."""
    record = PS1.index("Set-EnvCmdLines ([ordered]@{ FLUBNF_ENGINE = $Engine })")
    route_known = PS1.index("$EngineRouteBad = $EngineRoute")
    assert route_known < record
    for later in ('Say "plan', 'Say "controlled folder access', 'Say "python"',
                  '"-m", "pip"', "exit 1"):
        assert record < PS1.index(later), later
    clear = _ps1_block("if ($Engine) {\n    Say \"engine", "\n}\n")
    assert "Set-EnvCmdLines ([ordered]@{ FLUBNF_ENGINE = $Engine })" in clear
    assert 'GetEnvironmentVariable("FLUBNF_ENGINE", "User")' in clear
    assert 'SetEnvironmentVariable("FLUBNF_ENGINE", $null, "User")' in clear
    assert ('if ($acct -and ("$acct".Replace(\'"\', \'\').Trim()'
            '.ToLowerInvariant() -ne $Engine)) {') in clear
    # in that one place, and never written for the account
    assert PS1.count('GetEnvironmentVariable("FLUBNF_ENGINE", "User")') == 1
    assert re.findall(r'SetEnvironmentVariable\("FLUBNF_ENGINE", ([^,]+),',
                      PS1) == ["$null"]


def test_the_private_switch_stops_before_pip_when_the_engine_loads(tmp_path):
    """As setup_engine.sh --private: the private engine already loads, so
    the switch is the record and no more (no pip, no network, seconds).
    The probe is FluBNF.bat's, on the venv and checkout it uses."""
    block = _ps1_block('if ($Engine -eq "private") {\n    $Switched', "\n}\n")
    assert "(Test-Path -LiteralPath $VenvPy) -and (Test-Path -LiteralPath $EnginePy)" in block
    assert "Invoke-Captured $EnginePy @(\"-c\", $switchProbe, $PyBnf.TrimEnd('\\'))" in block
    assert block.index("if ($sw.Code -eq 0) {") < block.index("$Switched = $true") \
        < block.index("exit 0")
    for name in ("FLUBNF_ENGINE = \"private\"", "FLUBNF_PY_ENGINE = $EnginePy",
                 "FLUBNF_PYBNF = $PyBnf"):
        assert name in block, name
    assert ("this copy runs the private engine now, the fallback "
            "(FLUBNF_ENGINE=private);") in block
    start = PS1.index(block)
    for later in ('Say "python"', '"-m", "pip"', "exit 1", 'Say "FluSight hub data"'):
        assert start + block.index("exit 0") < PS1.index(later), later
    probe = "".join(re.findall(r'"([^"]*)"', re.search(
        r'\$switchProbe = ((?:"[^"]*"\s*\+\s*)*"[^"]*")', block).group(1)))
    bat_probe = re.search(r'"%ENGINEPY%" -c "([^"]+)" "%PYBNFDIR%" >nul 2>&1',
                          BAT).group(1)
    assert probe == bat_probe
    # and it loads a stand-in engine from an awkward folder
    checkout = tmp_path / "O'Neil files" / "PyBNF-Private"
    (checkout / "pybnf").mkdir(parents=True)
    (checkout / "pybnf" / "__init__.py").write_text("")
    (checkout / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
    (checkout / "bngsim.py").write_text("__version__ = '0.15.1'\n")
    out = subprocess.run([sys.executable, "-c", probe, str(checkout)],
                         capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr


def _record_patterns() -> list[tuple[str, str]]:
    """setup.ps1's record pattern, around [regex]::Escape(the name), in
    Get-EnvCmdValue (which reads) and Set-EnvCmdLines (which replaces)."""
    return re.findall(r"\$pat = '([^']*)' \+ \[regex\]::Escape\(\$(?:Name|name)\) "
                      r"\+ '([^']*)'", PS1)


# (line in .flubnf.env.cmd, the value it sets as setup.ps1 keeps it: None
# for no record, "" for one that sets nothing)
RECORD_FORMS = [
    ('set "FLUBNF_ENGINE=private"', "private"),
    ("set FLUBNF_ENGINE=private", "private"),
    ("set FLUBNF_ENGINE=private ", "private"),
    ('@set "FLUBNF_ENGINE=private"', "private"),
    ('SET "flubnf_engine=Private"', "private"),
    ('  set   "FLUBNF_ENGINE=PRIVATE"  ', "private"),
    ('set FLUBNF_ENGINE="private"', "private"),
    ('set "FLUBNF_ENGINE= public "', "public"),
    ('set "FLUBNF_ENGINE=pubic"', "pubic"),
    ('set "FLUBNF_ENGINE="', ""),
    ("set FLUBNF_ENGINE=", ""),
    ("@ set FLUBNF_ENGINE=private", "private"),
    # cmd sets the whole value: more than one word, or single quotes, names
    # no engine, so the public engine runs (and settings.py says so too)
    ('set "FLUBNF_ENGINE=private now"', "private now"),
    ("set FLUBNF_ENGINE='private'", "'private'"),
    ('rem set "FLUBNF_ENGINE=private"', None),
    ('set "FLUBNF_ENGINE_VENV=D:\\venvs\\flubnf-engine"', None),
    ('set "FLUBNF_PY_ENGINE=C:\\a b\\python.exe"', None),
]


@pytest.mark.parametrize("line, kept", RECORD_FORMS)
def test_setup_reads_every_record_form_cmd_runs(line, kept):
    """Finding 12: only `set "NAME=..."` was read. An unquoted line, which
    cmd and settings.py read, was no record to setup.ps1, and the rewrite
    at the end of its run dropped it: the copy went public with no word.
    The pattern is PowerShell's -match (any case); the value is kept as
    the script keeps it: quotes dropped, trimmed, an engine's name in
    lower case."""
    pats = _record_patterns()
    assert len(pats) == 2 and pats[0] == pats[1], pats   # read == replaced
    before, after = pats[0]
    pat = re.compile(before + re.escape("FLUBNF_ENGINE") + after, re.IGNORECASE)
    m = pat.match(line)
    raw = m.group(1) if m else None
    value = None if raw is None else raw.replace('"', "").strip()
    if value is not None and value.lower() in ("private", "public"):
        value = value.lower()
    assert value == kept
    if kept is not None:      # the route, as settings.engine_name reads it
        assert settings.engine_name(value) == ("private" if kept == "private"
                                               else "public")


@pytest.mark.parametrize("line, kept", RECORD_FORMS)
def test_the_console_reads_every_record_form_as_setup_does(
        tmp_path, monkeypatch, line, kept):
    """settings.py (flubnf doctor, the CLI, the console FluBNF.bat starts)
    reads each line to the engine setup.ps1 and FluBNF.bat read from it: a
    @ before set, and a value of two words (private to the console, public
    to the launcher, before), no longer read apart."""
    monkeypatch.setattr(settings, "_windows", lambda: True)
    (tmp_path / ".flubnf.env.cmd").write_bytes(
        b"@echo off\r\n" + line.encode() + b"\r\n")
    assert settings.recorded_engine(tmp_path) == (
        None if kept is None else settings.engine_name(kept))


def test_the_last_line_wins_and_the_route_counts_an_empty_record():
    body = _ps1_block("function Get-EnvCmdValue {", "\nfunction ")
    assert "if ($ln -match $pat) { $val = $Matches[1] }" in body
    route = _ps1_block("$EngineRoute = if ($Engine)", 'else { "public" }')
    order = [route.index(s) for s in (
        "if ($Engine) { $Engine }",
        "elseif ($EngineRecord) { $EngineRecord }",
        'elseif ($null -ne $EngineRecord) { "public" }',
        "elseif ($env:FLUBNF_ENGINE) { $env:FLUBNF_ENGINE }")]
    assert order == sorted(order), order
    norm = _ps1_block('$EngineRecord = Get-EnvCmdValue "FLUBNF_ENGINE"',
                      "$EngineRoute = if ($Engine)")
    assert "$EngineRecord = \"$EngineRecord\".Replace('\"', '').Trim()" in norm
    # written back as read, an empty one too (it clears an account value
    # for FluBNF.bat)
    env = _ps1_block('Say "environment"', 'Say "doctor"')
    keep = env.index('if ($EngineLine) { $EnvLines += "set `"FLUBNF_ENGINE=$EngineLine`"" }')
    empty = env.index('if (($null -ne $EngineLine) -and ("$EngineLine" -eq "")) '
                      '{ $EnvLines += "set `"FLUBNF_ENGINE=`"" }')
    assert keep < empty < env.index("[IO.File]::WriteAllText($EnvCmd")


def test_setup_names_the_fallbacks_folder_when_it_is_here():
    """As FluBNF.bat's lines: a fork on disk with no venv needs no file."""
    engine = _ps1_block('Say "engine venv', 'Say "environment"')
    fallback = engine[engine.index('if ($EngineRoute -eq "public") {'):
                      engine.index("} elseif ($EngineReady) {")]
    assert "if (Test-EngineOnDisk $PyBnf) {" in fallback
    assert "which installs it from there (no file needed)." in fallback
    assert ("the fallback needs the lab's engine file: save it in Downloads, "
            "run setup.ps1 -Engine private, open FluBNF.bat.") in fallback
    public = _ps1_block('Say "public engine', 'Say "engine venv')
    assert 'Info "  $SelfCmd -Engine private"' in public
    assert ('$SelfCmd = "powershell -NoProfile -ExecutionPolicy Bypass -File '
            '`"$($MyInvocation.MyCommand.Path)`""') in PS1


# ---------------------------------------------------- on Windows, for real
def _route_slice() -> str:
    """From the clearing of PUBLICROUTE to the private route's first test;
    the labels it ends at say which route was taken."""
    start = BAT.index('\nset "PUBLICROUTE="\n') + 1
    end = BAT.index("\nrem Installed? Cheap file tests first") + 1
    return (BAT[start:end] + "echo REACHED-PRIVATE [%PUBLICROUTE%]\nexit /b 0\n"
            + ":publicengine\necho REACHED-PUBLIC [%PUBLICROUTE%]\nexit /b 0\n")


ROUTE_VALUES = [None, "private", "Private", "public", "pubic", "private ",
                " private", "\tprivate", "  PRIVATE  ", '"private"',
                '" private "', '""', " ", "pri vate"]


@windows_only
@pytest.mark.parametrize("value", ROUTE_VALUES)
def test_windows_the_route_reads_the_value_as_settings_does(tmp_path, value):
    r = _cmd(tmp_path / "route.bat", "@echo off\nsetlocal\n" + _route_slice(),
             tmp_path, FLUBNF_ENGINE=value)
    want = "PRIVATE" if settings.engine_name(value) == "private" else "PUBLIC"
    assert f"REACHED-{want}" in r.stdout, (value, r.stdout, r.stderr)
    assert ("neither private nor public" in r.stdout) \
        == settings.engine_value_unknown(value), (value, r.stdout)


@windows_only
def test_windows_set_and_two_ampersands_takes_the_private_route(tmp_path):
    """Finding 6, as typed: cmd keeps the space before &&."""
    (tmp_path / "route.bat").write_bytes(
        ("@echo off\r\nsetlocal\r\n" + _route_slice().replace("\n", "\r\n"))
        .encode("ascii"))
    r = _cmd(tmp_path / "open.bat",
             '@echo off\nset FLUBNF_ENGINE=private && call "%~dp0route.bat"\n',
             tmp_path, FLUBNF_ENGINE=None)
    assert "REACHED-PRIVATE" in r.stdout, (r.stdout, r.stderr)
    assert "neither private nor public" not in r.stdout


@windows_only
def test_windows_a_stray_publicroute_is_cleared(tmp_path):
    r = _cmd(tmp_path / "route.bat", "@echo off\nsetlocal\n" + _route_slice(),
             tmp_path, FLUBNF_ENGINE="private", PUBLICROUTE="1")
    assert "REACHED-PRIVATE []" in r.stdout, (r.stdout, r.stderr)


@windows_only
def test_windows_a_quoted_public_record_does_not_close_the_window(tmp_path):
    """FLUBNF_PY_ENGINE_PUBLIC set by hand as "C:\\Program Files\\...": the
    IF in :recordpublic was a syntax error that ended the launcher after
    the engine verified, on every open. A stand-in setx comes first on
    PATH, so nothing reaches the account's environment."""
    py = tmp_path / "Program Files" / "pub" / "Scripts" / "python.exe"
    calls = tmp_path / "setx-calls.txt"
    shim = tmp_path / "shim"
    _exe(shim, "setx", f"import sys\nopen({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]))\n")
    start = BAT.index('\nset "PUBLICREC=%FLUBNF_PY_ENGINE_PUBLIC%"\n') + 1
    rec = BAT[start:].split("\nrem Installed, and the lock's?", 1)[0] + "\n"
    sub = BAT[BAT.index("\n:recordpublic\n") + 1:BAT.index("\n:failvenv\n") + 1]
    text = (f'@echo off\nsetlocal\nset "PUBLICPY={py}"\n' + rec
            + "call :recordpublic\necho REACHED-END\nexit /b 0\n" + sub)
    root = os.environ.get("SystemRoot", r"C:\Windows")
    r = _cmd(tmp_path / "record.bat", text, tmp_path,
             FLUBNF_PY_ENGINE_PUBLIC=f'"{py}"',
             PATH=rf"{shim};{root}\System32")
    out = r.stdout + r.stderr
    assert "REACHED-END" in r.stdout, out
    for crash in ("was unexpected", "syntax of the command"):
        assert crash not in out, out
    assert "recorded for flubnf doctor" not in out and not calls.exists(), out


@windows_only
@pytest.mark.parametrize("state", ["ready", "fork", "none"])
def test_windows_a_public_failure_says_which_state_the_fallback_is_in(
        tmp_path, state):
    pc = _public_pc(tmp_path, lock=False)
    py = pc.home / ".venvs" / "flubnf-engine" / "Scripts" / "python.exe"
    fork = pc.home / "GitHub" / "PyBNF-Private"
    if state == "ready":
        py.parent.mkdir(parents=True)
        py.write_bytes(b"")
    if state in ("ready", "fork"):
        (fork / "pybnf").mkdir(parents=True)
        (fork / "pybnf" / "pf.py").write_text("")

    r = _run_public(pc, PRIVATEPY=str(py), PYBNFDIR=str(fork))

    said = " ".join(r.stdout.split())
    assert "REACHED-CONSOLE" in r.stdout, r.stdout
    assert (READY_LINE in said) is (state == "ready"), said
    assert (FORK_LINE in said) is (state == "fork"), said
    assert (NOT_READY_LINE in said) is (state == "none"), said
    # this folder, as cmd spells it (%~dp0 may keep a short 8.3 name)
    typed = re.search(r'^    powershell -NoProfile -ExecutionPolicy Bypass '
                      r'-File "([^"]+)\\setup\.ps1" -Engine private$',
                      r.stdout, re.MULTILINE)
    assert typed and os.path.samefile(typed.group(1), pc.folder), r.stdout


def _account_engine() -> str | None:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, "FLUBNF_ENGINE")[0])
    except OSError:
        return None


def _powershell(script: Path, *args: str, cwd: Path, **env_extra
                ) -> subprocess.CompletedProcess:
    env = {**os.environ, "CI": "1"}
    env.update(env_extra)
    for name in [k for k, v in env.items() if v is None]:
        del env[name]
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(script), *args], cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        capture_output=True, text=True, errors="replace", timeout=600,
        check=False)


# (the record's text, the account's FLUBNF_ENGINE, the route both take)
RECORD_ROUTES = [
    ("set FLUBNF_ENGINE=private", None, "private"),
    ('set "FLUBNF_ENGINE="', "private", "public"),
    ('set "FLUBNF_ENGINE=PRIVATE"', None, "private"),
    ('@set "FLUBNF_ENGINE=private"', "public", "private"),
    ("set FLUBNF_ENGINE=private ", None, "private"),
    ("", "private", "private"),
    ('set "FLUBNF_ENGINE=pubic"', "private", "public"),
    ('set "FLUBNF_ENGINE=private"\r\nset "FLUBNF_ENGINE=public"', None, "public"),
]


@windows_only
@pytest.mark.parametrize("record, account, route", RECORD_ROUTES)
def test_windows_setup_and_the_launcher_read_a_record_the_same_way(
        tmp_path, record, account, route):
    """setup.ps1's reading (from the record's pattern through the route)
    against FluBNF.bat's (the file called, then its route), on one file."""
    envcmd = tmp_path / ".flubnf.env.cmd"
    envcmd.write_bytes(("@echo off\r\n" + record + "\r\n").encode("ascii"))
    start = PS1.index("function Get-OemEncoding {")
    end = PS1.index("\n# -Engine is recorded now")
    ps = tmp_path / "route.ps1"
    ps.write_bytes((f"$EnvCmd = '{envcmd}'\n$Engine = ''\n" + PS1[start:end]
                    + '\nWrite-Output "ROUTE=[$EngineRoute]"\n')
                   .replace("\n", "\r\n").encode("ascii"))
    r = _powershell(ps, cwd=tmp_path, FLUBNF_ENGINE=account)
    assert f"ROUTE=[{route}]" in r.stdout, (r.stdout, r.stderr)
    c = _cmd(tmp_path / "open.bat",
             f'@echo off\nsetlocal\ncall "{envcmd}"\n' + _route_slice(),
             tmp_path, FLUBNF_ENGINE=account)
    assert f"REACHED-{route.upper()}" in c.stdout, (c.stdout, c.stderr)


def _setup_folder(tmp_path: Path, console_python: str) -> Path:
    folder = tmp_path / "FluBNF"
    folder.mkdir()
    shutil.copy(REPO / "setup.ps1", folder)
    _exe(folder / ".venv" / "Scripts", "python", console_python)
    return folder


@windows_only
def test_windows_engine_private_is_recorded_when_the_run_stops_at_pip(tmp_path):
    """Finding 1. pip cannot reach PyPI (a console venv whose python fails
    every command stands in for it): setup.ps1 exits 1 at the console's
    install, and the choice is recorded all the same, in place of the
    line that was there, every other line kept."""
    if _account_engine() not in (None, "private"):
        pytest.skip("this account has FLUBNF_ENGINE set; the run would clear it")
    folder = _setup_folder(tmp_path, "import sys\nsys.exit(1)\n")
    envcmd = folder / ".flubnf.env.cmd"
    envcmd.write_bytes(b'@echo off\r\nset "FLUBNF_HUB=C:\\hub"\r\n'
                       b"set FLUBNF_ENGINE=public\r\n")

    r = _powershell(folder / "setup.ps1", "-Engine", "private", "-NoPrompt",
                    cwd=folder, FLUBNF_ENGINE=None, FLUBNF_PYBNF=None,
                    FLUBNF_HUB=str(tmp_path / "hub"), FLUBNF_NO_DATA="1",
                    FLUBNF_NO_PROBE="1",
                    FLUBNF_ENGINE_VENV=str(tmp_path / "no-engine-venv"))

    out = r.stdout + r.stderr
    assert r.returncode == 1, out
    lines = envcmd.read_bytes().decode("ascii").split("\r\n")
    assert [ln for ln in lines if "FLUBNF_ENGINE=" in ln] == [
        'set "FLUBNF_ENGINE=private"'], lines
    assert lines[:2] == ["@echo off", 'set "FLUBNF_HUB=C:\\hub"'], lines


@windows_only
def test_windows_engine_private_switches_with_no_pip_when_it_loads(tmp_path):
    """The private engine is installed and loads: -Engine private (in any
    case) records it, with its venv and checkout, and stops, before the
    console's python or pip is run; cmd then reads private from the file."""
    if _account_engine() not in (None, "private"):
        pytest.skip("this account has FLUBNF_ENGINE set; the run would clear it")
    ran = tmp_path / "console-python-ran.txt"
    folder = _setup_folder(tmp_path, f"open({str(ran)!r}, 'a').write('ran')\n")
    fork = tmp_path / "PyBNF-Private"
    (fork / "pybnf").mkdir(parents=True)
    (fork / "pybnf" / "pf.py").write_text("")
    venv = tmp_path / "venvs" / "flubnf-engine"
    _exe(venv / "Scripts", "python", f"""import os, sys
ok = (sys.argv[1:2] == ["-c"] and "from pybnf.pf import ParticleFilter" in sys.argv[2]
      and os.path.normcase(sys.argv[3]) == os.path.normcase({str(fork)!r}))
sys.exit(0 if ok else 5)
""")
    envcmd = folder / ".flubnf.env.cmd"
    envcmd.write_bytes(b'@echo off\r\nset "FLUBNF_HUB=C:\\hub"\r\n'
                       b'set "FLUBNF_ENGINE=public"\r\n'
                       b'set "FLUBNF_PY_ENGINE_PUBLIC=C:\\pub\\python.exe"\r\n')

    r = _powershell(folder / "setup.ps1", "-Engine", "PRIVATE", "-NoPrompt",
                    cwd=folder, FLUBNF_ENGINE=None, FLUBNF_PYBNF=str(fork),
                    FLUBNF_ENGINE_VENV=str(venv), FLUBNF_HUB=str(tmp_path / "hub"))

    out = r.stdout + r.stderr
    # whitespace dropped on both sides: PowerShell 5.1 wraps long host
    # lines mid-word when its output is redirected
    flat = re.sub(r"\s", "", out)
    assert r.returncode == 0, out
    assert re.sub(r"\s", "", "this copy runs the private engine now, the "
                  "fallback (FLUBNF_ENGINE=private);") in flat, out
    assert "==python==" not in flat and not ran.exists(), out
    lines = envcmd.read_bytes().decode("ascii").split("\r\n")
    assert 'set "FLUBNF_HUB=C:\\hub"' in lines
    assert 'set "FLUBNF_PY_ENGINE_PUBLIC=C:\\pub\\python.exe"' in lines
    assert [ln for ln in lines if "FLUBNF_ENGINE=" in ln] == [
        'set "FLUBNF_ENGINE=private"'], lines
    assert f'set "FLUBNF_PY_ENGINE={venv}\\Scripts\\python.exe"' in lines
    assert f'set "FLUBNF_PYBNF={fork}"' in lines
    c = _cmd(tmp_path / "read.bat",
             f'@echo off\nsetlocal\ncall "{envcmd}"\necho ENGINE=[%FLUBNF_ENGINE%]\n',
             tmp_path, FLUBNF_ENGINE=None)
    assert "ENGINE=[private]" in c.stdout, (c.stdout, c.stderr)
