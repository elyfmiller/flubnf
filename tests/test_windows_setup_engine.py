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
    kinds = {"git clone": 0, "-m venv": 0, "-m pip": 0, "conda create": 0}
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
    # conda's python.exe is a full path (Anaconda's can hold a space)
    assert '{ "`"$($c.exe)`"" }' in ENGINE


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
    for shape in ("pybnf-pf-*.tar.gz", "pybnf*.bundle"):
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
    assert 'Ok "engine file found: $EngineFile"' in ENGINE
    assert ("FluBNF.bat installs it, no GitHub account needed: right after "
            "this,") in ENGINE
    assert ("engine on disk: $PyBnf; FluBNF.bat finishes the install, no "
            "GitHub account needed") in ENGINE
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


def test_a_bundle_on_a_machine_without_git_is_not_promised():
    """FluBNF.bat clones a bundle with git; without git it cannot, so setup
    says so and names the archive, which needs none."""
    i = PS1.index('Ok "engine file found: $EngineFile"')
    body = PS1[i:PS1.index("} elseif ($access -eq", i)]
    assert 'if ($EngineFile -like "*.bundle" -and -not $GitPresent) {' in body
    assert "FluBNF.bat cannot clone this bundle" in body
    assert "pybnf-pf-XXXX.tar.gz, which needs no git" in body
    assert "on its next open" not in body, (
        "when FluBNF.bat runs setup.ps1 it installs in the same window")


def _bat_conda_folders() -> list[str]:
    """The folders FluBNF.bat's conda search names, in PowerShell's terms."""
    line = next(ln for ln in BAT.splitlines()
                if ln.startswith('for %%R in ("%USERPROFILE%\\anaconda3"'))
    return [re.sub(r"%(\w+)%", r"$env:\1", d)
            for d in re.findall(r'"([^"]+)"', line.split(" do ")[0])]


def test_conda_is_found_where_the_launcher_finds_it():
    """One root, in FluBNF.bat's order: CONDA_EXE, environments.txt, then the
    same folders, and a folder counts only with both python.exe and
    condabin\\conda.bat. setup.ps1 knew the same four folders as the
    launcher did, and missed the same installs."""
    body = _body("Find-CondaRoot")
    body = body[body.index("#>"):]          # the code, not its comment
    order = [body.index(s) for s in ("$env:CONDA_EXE", ".conda\\environments.txt",
                                     '"$env:USERPROFILE\\anaconda3"')]
    assert order == sorted(order), order
    listed = body[body.index('$roots += @("'):]
    listed = listed[:listed.index(")")]
    assert re.findall(r'"([^"]+)"', listed) == _bat_conda_folders()
    assert '"$root\\python.exe"' in body and '"$root\\condabin\\conda.bat"' in body
    assert "C:\\ProgramData\\anaconda3\\python.exe" not in PS1
    python = PS1[PS1.index('Say "python"'):PS1.index("foreach ($c in $Cands)")]
    assert "$CondaRoot = Find-CondaRoot" in python


def test_the_engine_python_is_gated_as_the_launcher_gates_it():
    """x64 3.11 or 3.12 only, the launcher's candidates in its order. The
    gate runs here under this Python with the version and platform
    swapped in."""
    gate = re.search(r'\$EngineGate = "([^"]+)"', ENGINE).group(1)
    assert "sysconfig.get_platform() == 'win-amd64'" in gate
    for version, platform, fits in [((3, 12, 10), "win-amd64", "1"),
                                    ((3, 11, 9), "win-amd64", "1"),
                                    ((3, 14, 0), "win-amd64", "0"),
                                    ((3, 12, 10), "win-arm64", "0"),
                                    ((3, 12, 10), "win32", "0")]:
        swap = (f"import sys, sysconfig; sys.version_info = {version!r}; "
                f"sysconfig.get_platform = lambda: {platform!r}; "
                "exec(sys.argv.pop(1))")
        out = subprocess.run([sys.executable, "-c", swap, gate],
                             capture_output=True, text=True, timeout=60,
                             check=False)
        assert out.stdout.strip() == fits, (version, platform, out)
    cands = ENGINE[ENGINE.index("$bootCands = @("):ENGINE.index("foreach ($c in $bootCands)")]
    order = [cands.index(s) for s in ('@("-3.12")', '@("-3.11")', 'exe = "python"',
                                      'Join-Path $CondaRoot "python.exe"')]
    assert order == sorted(order), order
    assert "[version]" not in ENGINE, "a version-only check is left"


def test_with_no_engine_python_the_remedy_fits_this_pc():
    """With no x64 3.11/3.12 and no conda, FluBNF.bat stops, so setup.ps1
    says so in every branch, the engine file's included, and does not
    promise that FluBNF.bat finishes the install. `py install 3.12` only
    where the install manager is (the older py.exe runs "install" as a
    script), never on an ARM PC; Anaconda, or Anaconda Prompt, otherwise."""
    said = ENGINE.index("if ($EngineNoPython) {")
    assert said < ENGINE.index('if ($access -eq "local") {')
    remedy = _block(ENGINE, said)
    manager = _block(remedy, remedy.index(
        "if ((-not $arm) -and (Get-Command pymanager"))
    assert "py install 3.12" in manager
    assert remedy.count("py install") == 1 and ENGINE.count("py install") == 1
    assert "anaconda.com/download" in remedy and "Anaconda Prompt" in remedy
    assert '$env:PROCESSOR_ARCHITECTURE -eq "ARM64"' in remedy
    assert ENGINE.count("FluBNF.bat installs it once a Python above is in place") == 2
    by_hand = ENGINE[ENGINE.index('if ($access -ne "file" -and $EngineNoPython) {'):]
    assert "(first a Python, as above; FluBNF.bat then does the rest)" in by_hand


def test_the_printed_commands_build_what_the_launcher_builds():
    """conda asked for x64 with CONDA_SUBDIR=win-64, as the launcher asks:
    conda before 23.10 stops at --subdir on create ("unrecognized
    arguments"), and every release reads the variable. pip through python
    -m: Scripts\\pip.exe is a launcher antivirus can take, and FluBNF.bat no
    longer runs it."""
    commands = _commands()
    conda = [ln for ln in commands if ln.strip().startswith("conda create")]
    assert len(conda) == 1 and conda[0].rstrip().endswith("python=3.12"), conda
    printed = [ln.strip() for ln in _printed(ENGINE)]
    assert not [ln for ln in printed if "--subdir" in ln], printed
    subdir = 'set "CONDA_SUBDIR=win-64"'
    assert subdir in BAT and subdir in printed, printed
    assert printed.index(subdir) < printed.index(conda[0].strip()), printed
    # set is Set-Variable in PowerShell: that prompt is given its own form
    assert any('$env:CONDA_SUBDIR = "win-64"' in ln for ln in printed), printed
    pips = [ln for ln in commands if " pip " in f" {ln} "]
    assert len(pips) == 2, pips
    for ln in pips:
        assert '\\Scripts\\python.exe" -m pip install ' in ln, ln
    assert "pip.exe`\" install" not in ENGINE


def test_a_venv_that_cannot_import_names_a_missing_visual_cpp_runtime():
    """Keyed on msvcp140.dll in System32, as FluBNF.bat is, with the same
    link: libroadrunner imports it, and a python.org Python does not bring
    it."""
    branch = ENGINE[ENGINE.index("its imports fail. Python said:"):
                    ENGINE.index("if ($EngineReady) {")]
    assert 'Join-Path $env:SystemRoot "System32\\msvcp140.dll"' in branch
    assert "Test-Path -LiteralPath $vcrt" in branch
    link = "https://aka.ms/vc14/vc_redist.x64.exe"
    assert link in branch and link in BAT


# ------------------------------------------ the public engine (-Engine public)
PUBLIC = PS1[PS1.index('Say "public engine'):PS1.index('Say "engine venv')]
ENV = PS1[PS1.index('Say "environment"'):PS1.index('Say "doctor"')]
PUBLIC_EXPANSIONS = {
    "PublicVenv": PROFILE + r"\AppData\Local\FluBNF\venv-public",
    "PublicPy": PROFILE + r"\AppData\Local\FluBNF\venv-public\Scripts\python.exe",
    "PublicConda": PROFILE + r"\AppData\Local\FluBNF\python312-public",
    "EngineLock": PROFILE + r"\AppData\Local\FluBNF\flubnf\engine-requirements.txt",
    "LockTool": PROFILE + r"\AppData\Local\FluBNF\flubnf\scripts\engine_lock.py",
    "PublicBootCmd": "py -3.12",
    "force": "",
}


def _public_commands() -> list[str]:
    out = []
    for m in re.finditer(r'^\s*Info "(.*)"\s*$', PUBLIC, flags=re.MULTILINE):
        text = m.group(1).replace('`"', '"')
        text = re.sub(r"\$(env:\w+|\w+)",
                      lambda v: PUBLIC_EXPANSIONS.get(v.group(1), v.group(0)),
                      text)
        if text.startswith("  ") and text.strip().startswith(
                ("py ", "conda ", '"', "set ")):
            out.append(text.strip())
    return out


def test_setup_takes_an_engine_and_otherwise_keeps_the_choice_made():
    """-Engine private|public; without it the record in .flubnf.env.cmd,
    which FluBNF.bat reads on every open and so outranks the account's
    variable, then FLUBNF_ENGINE, then private. A value that is neither is
    said and read as private, as the launcher reads it."""
    head = PS1[:PS1.index("function Say")]
    assert '[ValidateSet("private", "public")][string]$Engine = ""' in head
    assert "-Engine private|public" in head
    route = PS1[PS1.index("$EngineRoute = if ($Engine)"):]
    order = [route.index(s) for s in (
        "if ($Engine) { $Engine }", "elseif ($EngineRecord) { $EngineRecord }",
        "elseif ($env:FLUBNF_ENGINE) { $env:FLUBNF_ENGINE }",
        'else { "private" }')]
    assert order == sorted(order), order
    assert PS1.index('$EngineRecord = Get-EnvCmdValue "FLUBNF_ENGINE"') \
        < PS1.index("$EngineRoute = if ($Engine)")
    assert '$EngineRoute = "private"' in route[:route.index('Say "plan')]
    assert "neither private nor public" in PS1[:PS1.index('Say "controlled')]


def test_setup_reads_flubnf_env_cmd_as_cmd_does():
    """The last `set "NAME=..."` wins, the form both setup.ps1 and
    FluBNF.bat write; read in the OEM code page they are written in."""
    body = _body("Get-EnvCmdValue")
    assert "[IO.File]::ReadAllLines($EnvCmd, (Get-OemEncoding))" in body
    m = re.search(r"\$pat = '(.*?)' \+ \[regex\]::Escape\(\$Name\) \+ '(.*?)'",
                  body)
    pat = re.compile(m.group(1) + re.escape("FLUBNF_PY_ENGINE_PUBLIC") + m.group(2))
    written = [
        'set "FLUBNF_PY_ENGINE_PUBLIC=C:\\Users\\Jane Doe\\AppData\\Local\\FluBNF\\venv-public\\Scripts\\python.exe"',
        'rem FluBNF.bat verified the public engine below; a later set wins.',
        'set "FLUBNF_PY_ENGINE_PUBLIC=D:\\venv (2)\\Scripts\\python.exe"']
    found = [pm.group(1) for ln in written if (pm := pat.match(ln))]
    assert found[-1] == "D:\\venv (2)\\Scripts\\python.exe", found
    assert len(found) == 2
    # what the launcher appends has exactly that shape
    assert ('echo set "FLUBNF_PY_ENGINE_PUBLIC=%PUBLICPY%">>".flubnf.env.cmd"'
            in BAT)
    assert "$val = $Matches[1]" in body
    assert ('[IO.File]::WriteAllText($EnvCmd, (($EnvLines -join "`r`n") + '
            '"`r`n"), (Get-OemEncoding))') in ENV, "the write uses the same code page"


def test_setup_keeps_the_public_lines_it_did_not_change():
    """.flubnf.env.cmd is rewritten whole, so the switch and the public
    engine's Python are carried over unless this run changed them: -Engine
    public writes FLUBNF_ENGINE, -Engine private drops it, and nothing else
    touches it. It is never the account's variable; -Engine private clears
    one set there by hand."""
    assert ('$EngineLine = if ($Engine -eq "public") { "public" }' in ENV
            and 'elseif ($Engine -eq "private") { $null }' in ENV
            and "else { $EngineRecord }" in ENV)
    assert 'if ($EngineLine) { $EnvLines += "set `"FLUBNF_ENGINE=$EngineLine`"" }' in ENV
    assert "$PublicLine = if ($PublicReady) { $PublicPy }" in ENV
    assert 'else { Get-EnvCmdValue "FLUBNF_PY_ENGINE_PUBLIC" }' in ENV
    assert ('if ($PublicLine) { $EnvLines += '
            '"set `"FLUBNF_PY_ENGINE_PUBLIC=$PublicLine`"" }') in ENV
    write = ENV.index("[IO.File]::WriteAllText($EnvCmd")
    assert ENV.index("$EnvLines += \"set `\"FLUBNF_ENGINE=") < write
    sets = re.findall(r'SetEnvironmentVariable\("FLUBNF_ENGINE", ([^,]+),', PS1)
    assert sets == ["$null"], sets
    clear = _block(ENV, ENV.index('if ($Engine -eq "private") {'))
    assert 'GetEnvironmentVariable("FLUBNF_ENGINE", "User")' in clear
    record = _block(ENV, ENV.index("if ($PublicReady) {"))
    assert 'SetEnvironmentVariable("FLUBNF_PY_ENGINE_PUBLIC", $PublicPy, "User")' in record
    assert PS1.count('$EnvCmd = Join-Path $Here ".flubnf.env.cmd"') == 1
    assert PS1.index('$EnvCmd = Join-Path $Here ".flubnf.env.cmd"') \
        < PS1.index('$EngineRecord = Get-EnvCmdValue "FLUBNF_ENGINE"')


def test_the_public_section_never_reaches_for_the_private_fork():
    """No GitHub probe, clone, engine file or attempt record on the public
    route: the private engine is reported as the fallback and left alone.
    The lock is read only through scripts\\engine_lock.py, with the console
    venv's Python, and a venv inside a private one is refused first."""
    code = "\n".join(ln for ln in PUBLIC.splitlines()
                     if not ln.lstrip().startswith("#"))
    for word in ("Test-RemoteAccess", "git clone", "PyBNF-Private",
                 "Find-EngineFile", "Clear-EngineAttempt", "github.com",
                 ".whl", "sha256"):
        assert word not in code, word
    taken = PUBLIC.index("if ($PublicVenvTaken) {")
    wheel = PUBLIC.index('Invoke-Captured $VenvPy @($LockTool, "wheel", $EngineLock)')
    check = PUBLIC.index('Invoke-Captured $PublicPy @($LockTool, "check", $EngineLock)')
    assert taken < wheel < check
    assert '$LockTool = Join-Path $Here "scripts\\engine_lock.py"' in PS1
    guard = PS1[PS1.index("$PublicVenvTaken = $null"):PS1.index('Say "plan')]
    assert 'Resolve-ProfilePath ".venvs\\flubnf"' in guard
    assert 'Resolve-ProfilePath ".venvs\\flubnf-engine"), $EngineVenv' in guard
    assert "Test-PathInside $PublicVenv $v" in guard
    assert 'Join-Path $FluBnfRoot "venv-public"' in PS1
    fallback = ENGINE[ENGINE.index('if ($EngineRoute -eq "public") {'):
                      ENGINE.index("} elseif ($EngineReady) {")]
    assert "Warn" not in fallback and "Invoke-Captured" not in fallback
    assert ENGINE.index('if ($EngineRoute -eq "public") {') \
        < ENGINE.index('Warn "engine venv not ready."')


def test_the_public_commands_are_hash_checked_and_survive_a_space():
    """The by-hand steps build what FluBNF.bat builds: x64 3.12, conda's
    own 3.12 under %LOCALAPPDATA%\\FluBNF (never the private engine's),
    pip from the lock with every hash checked and nothing built, then the
    check. Each path stays one argument with a space in the profile."""
    commands = _public_commands()
    pip = [ln for ln in commands if " -m pip install " in ln]
    assert len(pip) == 1, commands
    args = _cmd_split(pip[0])
    assert args[0] == PUBLIC_EXPANSIONS["PublicPy"]
    assert args[1:] == ["-m", "pip", "install", "--require-hashes",
                        "--only-binary", ":all:", "-r",
                        PUBLIC_EXPANSIONS["EngineLock"]], args
    check = [ln for ln in commands if " check " in ln]
    assert _cmd_split(check[0]) == [PUBLIC_EXPANSIONS["PublicPy"],
                                    PUBLIC_EXPANSIONS["LockTool"], "check",
                                    PUBLIC_EXPANSIONS["EngineLock"]]
    venv = [ln for ln in commands if " -m venv " in ln]
    assert [_cmd_split(ln)[-1] for ln in venv] == [PUBLIC_EXPANSIONS["PublicVenv"]] * 2
    conda = [ln for ln in commands if ln.startswith("conda create")]
    assert _cmd_split(conda[0])[4] == PUBLIC_EXPANSIONS["PublicConda"], conda
    assert 'set "CONDA_SUBDIR=win-64"' in commands
    assert ".venvs" not in " ".join(commands)
    assert ' --force-reinstall' in PUBLIC   # a venv that is there but wrong
    assert BAT.count('if defined PUBLICROUTE set "CONDAENV=%LOCALAPPDATA%'
                     '\\FluBNF\\python312-public"') == 1


def test_the_public_python_is_gated_as_the_launcher_gates_it():
    """x64 3.12 alone, in the launcher's order: py -3.12, python, conda's
    base. The gate runs here with the version and platform swapped in."""
    gate = re.search(r'\$PublicGate = "([^"]+)"', PUBLIC).group(1)
    for version, platform, fits in [((3, 12, 10), "win-amd64", "1"),
                                    ((3, 11, 9), "win-amd64", "0"),
                                    ((3, 13, 1), "win-amd64", "0"),
                                    ((3, 12, 10), "win-arm64", "0")]:
        swap = (f"import sys, sysconfig; sys.version_info = {version!r}; "
                f"sysconfig.get_platform = lambda: {platform!r}; "
                "exec(sys.argv.pop(1))")
        out = subprocess.run([sys.executable, "-c", swap, gate],
                             capture_output=True, text=True, timeout=60,
                             check=False)
        assert out.stdout.strip() == fits, (version, platform, out)
    cands = PUBLIC[PUBLIC.index("$pubCands = @("):PUBLIC.index("foreach ($c in $pubCands)")]
    order = [cands.index(s) for s in ('@("-3.12")', 'exe = "python"',
                                      'Join-Path $CondaRoot "python.exe"')]
    assert order == sorted(order) and '"-3.11"' not in cands
