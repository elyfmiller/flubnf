"""setup.ps1's engine section must agree with FluBNF.bat, which installs it.

The launcher installs the private PyBNF fork from an engine file (no GitHub
account) or from a checkout already on disk, and looks past a FLUBNF_PYBNF
that holds no engine. setup.ps1 used to probe GitHub whatever was on disk,
record FLUBNF_PYBNF for an empty default folder (which `flubnf doctor` then
followed), and print commands with unquoted paths. No PowerShell runs here,
so setup.ps1 is checked as text; the commands it prints are rebuilt with a
profile path holding a space and split the way Command Prompt splits them,
and the import probe runs under this Python. Windows CI executes setup.ps1.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PS1 = (REPO / "setup.ps1").read_text(encoding="utf-8")
BAT = (REPO / "FluBNF.bat").read_text(encoding="utf-8")

ENGINE = PS1[PS1.index('Say "engine venv'):PS1.index('Say "environment"')]

# What the printed commands expand to on a machine whose profile path has a
# space in it, the case that broke them.
PROFILE = r"C:\Users\Jane Doe"
EXPANSIONS = {
    "PyBnf": PROFILE + r"\AppData\Local\FluBNF\PyBNF-pf",
    "EngineVenv": PROFILE + r"\.venvs\flubnf-engine",
    "env:USERPROFILE": PROFILE,
    "PyBnfRemote": "https://github.com/elyfmiller/PyBNF-Private.git",
    "EngineBootCmd": "py -3.12",
}


def _body(name: str) -> str:
    """The text of one PowerShell function, up to the next top-level one."""
    start = PS1.index(f"function {name} {{")
    nxt = PS1.find("\nfunction ", start + 1)
    return PS1[start:nxt if nxt > 0 else len(PS1)]


def _printed(section: str) -> list[str]:
    """What each Info line in `section` shows, with its paths expanded."""
    out = []
    for m in re.finditer(r'^\s*Info "(.*)"\s*$', section,
                         flags=re.MULTILINE):
        text = m.group(1).replace('`"', '"')
        text = re.sub(r"\$(env:\w+|\w+)",
                      lambda v: EXPANSIONS.get(v.group(1), v.group(0)), text)
        out.append(text)
    return out


def _block(text: str, start: int) -> str:
    """The brace block that opens at the first { at or after `start`,
    braces inside double-quoted strings not counted."""
    i = text.index("{", start)
    depth, quoted, j = 0, False, i
    while j < len(text):
        ch = text[j]
        if ch == "`":
            j += 2
            continue
        if ch == '"':
            quoted = not quoted
        elif not quoted and ch == "{":
            depth += 1
        elif not quoted and ch == "}":
            depth -= 1
            if depth == 0:
                return text[i:j + 1]
        j += 1
    raise AssertionError(f"unbalanced block at {text[i:i + 80]!r}")


def _cmd_split(line: str) -> list[str]:
    """Split a command line as Command Prompt hands it to a program:
    whitespace separates arguments except inside double quotes."""
    args, cur, quoted = [], "", False
    for ch in line.strip():
        if ch == '"':
            quoted = not quoted
        elif ch.isspace() and not quoted:
            if cur:
                args.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        args.append(cur)
    return args


def _commands() -> list[str]:
    starts = ("git clone", "py ", "conda ", '"')
    return [line for line in _printed(ENGINE)
            if line.startswith("  ") and line.strip().startswith(starts)]


def test_every_printed_engine_command_survives_a_profile_path_with_a_space():
    """Unquoted, C:\\Users\\Jane Doe split in two: git clone stopped at
    "Too many arguments" and venv quietly made two folders."""
    commands = _commands()
    kinds = {"git clone": 0, "-m venv": 0, "pip.exe": 0, "conda create": 0}
    for line in commands:
        for kind in kinds:
            kinds[kind] += kind in line
        for arg in _cmd_split(line):
            if "Jane" in arg:
                assert "Jane Doe" in arg, (
                    f"setup.ps1 prints {line.strip()!r}; Command Prompt "
                    f"splits it at the space in {PROFILE!r} and hands the "
                    f"program {arg!r}")
    for kind, n in kinds.items():
        assert n, (f"no printed engine command contains {kind!r}; the "
                   f"commands found were {commands}")


def test_the_printed_commands_are_for_command_prompt_and_say_so():
    """The docs start setup.ps1 from Command Prompt, where a leading & is a
    syntax error; PowerShell needs one before a quoted program path."""
    for line in _commands():
        assert not line.strip().startswith("&"), line
    assert "In PowerShell, put & and a space in front of a line" in ENGINE
    assert "in Command Prompt" in ENGINE
    # the fallback interpreter is a full path (Anaconda's can hold a space)
    assert '{ "`"$PyExe`"" }' in ENGINE


def test_the_engine_probe_takes_the_checkout_as_an_argument(tmp_path):
    """r'<path>' spliced into the probe was a SyntaxError for an apostrophe
    or a trailing backslash, so a working engine read as broken."""
    assert "r'$PyBnf'" not in PS1
    m = re.search(r'\$probe = ((?:"[^"]*"\s*\+\s*)*"[^"]*")', ENGINE)
    assert m, "setup.ps1's engine import probe was not found"
    probe = "".join(re.findall(r'"([^"]*)"', m.group(1)))
    assert "sys.argv[1]" in probe
    assert "@(\"-c\", $probe, $PyBnf.TrimEnd('\\'))" in ENGINE, (
        "the probe no longer passes the checkout, trimmed of a trailing "
        "backslash, as its argument")
    # the probe itself, against a stand-in engine in an awkward folder
    checkout = tmp_path / "O'Neil files" / "PyBNF-pf"
    (checkout / "pybnf").mkdir(parents=True)
    (checkout / "pybnf" / "__init__.py").write_text("")
    (checkout / "pybnf" / "pf.py").write_text("class ParticleFilter: pass\n")
    (checkout / "bngsim.py").write_text("__version__ = '0.15.1'\n")
    out = subprocess.run([sys.executable, "-c", probe, str(checkout)],
                         capture_output=True, text=True, timeout=60,
                         check=False)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "pf ok, bngsim 0.15.1"


def test_an_engine_file_is_looked_for_where_the_launcher_looks():
    """The file a student saved is found in the folders FluBNF.bat searches,
    so setup.ps1 never calls it missing while the launcher installs it."""
    body = _body("Find-EngineFile")
    for shape in ("pybnf*.tar.gz", "pybnf*.bundle"):
        assert f'"{shape}"' in body, f"setup.ps1 never looks for {shape}"
        assert shape in BAT
    for folder in ("Downloads", "Desktop", "Documents"):
        assert f'"{folder}"' in body, f"setup.ps1 never looks in {folder}"
    assert "Split-Path -Parent $Here" in body, (
        "setup.ps1 does not look beside the FluBNF folder, as FluBNF.bat does")
    assert "if ($env:OneDrive)" in body, (
        "setup.ps1 misses Known Folder Move (or probes an unset %OneDrive%)")
    assert "$env:FLUBNF_PYBNF_BUNDLE" in body
    # the newest archive wins in both
    assert "LastWriteTimeUtc -Descending" in body
    assert "call :newerarchive" in BAT


def test_a_found_engine_file_or_checkout_skips_the_github_probe():
    """A student with the engine file is never sent to GitHub."""
    assert ("engine file found: $EngineFile; FluBNF.bat installs it on its "
            "next open, no GitHub account needed") in ENGINE
    assert ("engine on disk: $PyBnf; FluBNF.bat finishes the install on its "
            "next open, no GitHub account needed") in ENGINE
    assert ENGINE.count("Test-RemoteAccess $PyBnfRemote") == 1
    after_file = ENGINE.index("} elseif ($EngineFile) {")
    neither = _block(ENGINE, ENGINE.index("} else {", after_file) + 1)
    assert "Test-RemoteAccess $PyBnfRemote" in neither, (
        "the GitHub probe is no longer confined to the branch where neither "
        "an engine on disk nor an engine file was found")
    assert "if ($EngineOnDisk) {" in ENGINE[:after_file]
    # and the found-file branch prints no GitHub clone or by-hand commands
    assert 'if ($access -ne "file") {' in ENGINE


def test_an_unpacked_archive_counts_as_an_engine_on_disk():
    """The archive has no .git; its pybnf\\pf.py is what FluBNF.bat tests."""
    body = _body("Test-EngineOnDisk")
    assert '".git"' in body and '"pybnf\\pf.py"' in body
    assert 'Test-Path (Join-Path $PyBnf ".git")' not in PS1, (
        "setup.ps1 treats only a git clone as local again, so an unpacked "
        "archive gets the GitHub diagnosis")
    # FluBNF.bat's own test, which the two must share
    assert 'if exist "%PYBNFDIR%\\pybnf\\pf.py" goto :pybnfresolved' in BAT


def test_setup_clears_the_launchers_failed_attempt_record():
    """setup.ps1 deletes FluBNF.bat's failed-install record (the same file,
    .venv\\engine-attempt.txt in the FluBNF folder), so the next open of
    FluBNF.bat tries the install again."""
    assert 'set "ATTEMPT=%CD%\\.venv\\engine-attempt.txt"' in BAT
    body = _body("Clear-EngineAttempt")
    assert 'Join-Path $VenvDir "engine-attempt.txt"' in body
    assert "Remove-Item -LiteralPath $stamp" in body
    assert ENGINE.count("Clear-EngineAttempt") == 2, (
        "the record is cleared in the found-file and on-disk branches only, "
        "where the launcher has something to install from")


def test_a_pin_to_a_folder_without_an_engine_is_neither_followed_nor_recorded():
    """FluBNF.bat looks past such a pin; setup.ps1 followed it and then
    recorded it, so `flubnf doctor` reported a working engine as missing."""
    body = _body("Resolve-PyBnf")
    honour = body.index("if (Test-EngineOnDisk $pin) { return $pin }")
    search = body.index('foreach ($name in @("PyBNF-pf", "PyBNF-Private"))')
    assert honour < search
    assert "if ($FromEnv) { return $FromEnv }" not in body
    env = PS1[PS1.index('Say "environment"'):PS1.index('Say "doctor"')]
    gate = env.index("$PyBnfRecorded = Test-EngineOnDisk $PyBnf")
    write = env.index('SetEnvironmentVariable("FLUBNF_PYBNF", $PyBnf, "User")')
    guard = env.index("if ($PyBnfRecorded) {")
    assert gate < guard < write, "the FLUBNF_PYBNF write is unconditional again"
    line = 'if ($PyBnfRecorded) { $EnvLines += "set `"FLUBNF_PYBNF=$PyBnf`"" }'
    assert line in env, (
        ".flubnf.env.cmd records FLUBNF_PYBNF whether or not an engine is there")
    assert "FLUBNF_PYBNF not recorded:" in env
    assert 'SetEnvironmentVariable("FLUBNF_PYBNF", $null' not in PS1, (
        "setup.ps1 deletes FLUBNF_PYBNF; withholding the write is the fix, "
        "a deliberate pin to an unplugged drive must survive")


def test_moving_the_repository_out_of_documents_says_to_drop_its_venv():
    """pip's launchers in .venv\\Scripts hold the old absolute path, so a
    moved repository's console fails with 'Fatal error in launcher'."""
    remedy = PS1[PS1.index("The repository itself has no variable"):
                 PS1.index("2. Allow the specific programs through")]
    flat = " ".join(" ".join(_printed(remedy)).split())
    assert "delete the .venv folder inside it" in flat
    assert "FluBNF.bat builds a fresh one on its next open" in flat
