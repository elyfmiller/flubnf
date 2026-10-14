"""SHIPPED (used by the FluBNF console, app/).

Machine-specific paths, resolved once, overridable by environment.

Everything external that flubnf needs to run lives here so a new machine
configures the system by exporting a handful of variables (or editing a
`.env`-style shell profile) instead of patching source:

    FLUBNF_HUB        path to a clone of cdcepi/FluSight-forecast-hub
    FLUBNF_BNG        path to BioNetGen's BNG2.pl
    FLUBNF_PY_ENGINE  python of the engine venv (pybnf + bngsim installed)
    FLUBNF_PYBNF      checkout of the PyBNF fork providing fit_type=pf

Defaults are conventional locations (~/GitHub on POSIX; see _checkout),
so a conventionally laid-out machine needs none.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _windows() -> bool:
    """Is this Windows? A seam for tests: faking os.name would turn every
    later pathlib.Path into a WindowsPath."""
    return sys.platform.startswith("win")


def _home() -> Path:
    """Profile root for checkout defaults (%USERPROFILE% / $HOME), the root
    FluBNF.bat and setup.ps1 ($ProfileRoot) default to. setup.ps1 also
    searches both $HOME and %USERPROFILE%; a checkout under the other one is
    reached here only through the variable setup.ps1 records.

    A seam for tests: ntpath.expanduser ignores $HOME, so faking $HOME does
    not redirect this on Windows.
    """
    return Path("~").expanduser()


def _path(env: str, *fallbacks: str) -> Path:
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    for f in fallbacks:
        p = Path(f).expanduser()
        if p.exists():
            return p
    return Path(fallbacks[0]).expanduser()


def _checkout(env: str, name: str) -> Path:
    """`env` when it is set, else where the checkout lives by default
    (_default_checkout)."""
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    return _default_checkout(name)


def _default_checkout(name: str) -> Path:
    """Where a git checkout lives when no variable names it.

    POSIX: ~/GitHub/<name>, because macOS keeps FluBNF.app out of
    Documents (FluBNF.command moves an older checkout there). Windows:
    %LOCALAPPDATA%\\FluBNF\\<name>, because Controlled Folder Access
    (Defender), where enabled, blocks git.exe and python.exe from writing
    under Documents. Microsoft ships it off; %LOCALAPPDATA% works either
    way (never protected, does not roam). An existing checkout at the old
    Documents path still wins when the new one does not exist; nothing here
    moves a directory (docs/WINDOWS.md).
    """
    legacy = _home() / "Documents" / "GitHub" / name
    if not _windows():
        home = _home() / "GitHub" / name
        return legacy if legacy.exists() and not home.exists() else home
    if legacy.exists():
        return legacy
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else _home() / "AppData" / "Local"
    return base / "FluBNF" / name


HUB = _checkout("FLUBNF_HUB", "FluSight-forecast-hub")
ARCHIVE = HUB / "auxiliary-data/target-data-archive"
LOCATIONS = HUB / "auxiliary-data/locations.csv"

def bng_platform_dirs(platform: str | None = None) -> tuple:
    """bionetgen's per-platform bundle folders, this platform's first (its
    run_network binary is the one that runs here); the others follow only
    as a last resort."""
    platform = sys.platform if platform is None else platform
    own = ("bng-mac" if platform == "darwin"
           else "bng-win" if platform.startswith(("win", "cygwin"))
           else "bng-linux")
    return (own,) + tuple(d for d in ("bng-mac", "bng-linux", "bng-win")
                          if d != own)


def _bng_candidates(platform: str | None = None):
    """BNG2.pl from `pip install bionetgen` in this app's .venv, this
    platform's layout first (Lib on Windows, lib/python3.N elsewhere), then
    the development host's anaconda. First existing path wins, so this
    platform's bundle leads; with none there, the first candidate is the
    path a message names, so it is one that can exist here."""
    minor = sys.version_info[1]
    here = Path(__file__).resolve().parents[1]
    dirs = bng_platform_dirs(platform)
    win = (sys.platform if platform is None else platform).startswith("win")
    for venv in (here / ".venv",):
        posix = venv / "lib" / f"python3.{minor}" / "site-packages"
        nt = venv / "Lib" / "site-packages"
        for sp in ((nt, posix) if win else (posix, nt)):
            for plat in dirs:
                yield str(sp / "bionetgen" / plat / "BNG2.pl")
    for plat in dirs:
        if plat != "bng-win":
            yield ("/opt/anaconda3/lib/python3.12/site-packages/bionetgen/"
                   f"{plat}/BNG2.pl")


BNG = _path(
    "FLUBNF_BNG",
    *_bng_candidates(),
    shutil.which("BNG2.pl") or "BNG2.pl",
)


def _engine_python_candidates(windows: bool | None = None) -> tuple:
    """Where the engine venv's Python is looked for when FLUBNF_PY_ENGINE
    is unset; the first that exists wins, and with none the first is the
    path messages name.

    macOS and Linux, as always: ~/.venvs/flubnf (the development host,
    where sealed results were made), then setup_engine.sh's
    ~/.venvs/flubnf-engine (the Scripts forms never exist there).

    Windows: the venv FluBNF.bat and setup.ps1 build first,
    %FLUBNF_ENGINE_VENV% when set, else ~/.venvs/flubnf-engine, then
    ~/.venvs/flubnf; the Scripts layout only, the one Windows has, so a
    message never names a bin/python there. `windows` is injectable for
    tests."""
    if not (_windows() if windows is None else windows):
        return ("~/.venvs/flubnf/bin/python",
                "~/.venvs/flubnf-engine/bin/python",
                "~/.venvs/flubnf/Scripts/python.exe",
                "~/.venvs/flubnf-engine/Scripts/python.exe")
    own = os.environ.get("FLUBNF_ENGINE_VENV", "").strip().rstrip("\\/")
    venvs = ([own] if own else []) + ["~/.venvs/flubnf-engine",
                                      "~/.venvs/flubnf"]
    return tuple(f"{v}/Scripts/python.exe" for v in venvs)


PY_ENGINE = _path("FLUBNF_PY_ENGINE", *_engine_python_candidates())


def _holds_engine(p: Path) -> bool:
    """A git checkout or an unpacked archive: the test both launchers apply
    (FluBNF.bat, FluBNF.command), never the bare folder."""
    try:
        return (p / ".git").exists() or (p / "pybnf" / "pf.py").is_file()
    except OSError:
        return False


def _engine_search(names) -> list:
    """Every place a launcher looks for the engine, in its order:
    FluBNF.bat tries each name under Documents\\GitHub, then under
    %LOCALAPPDATA%\\FluBNF; FluBNF.command tries every name under ~/GitHub,
    then under ~/Documents/GitHub."""
    docs = _home() / "Documents" / "GitHub"
    if _windows():
        local = os.environ.get("LOCALAPPDATA")
        base = (Path(local) if local else _home() / "AppData" / "Local") \
            / "FluBNF"
        return [root / n for n in names for root in (docs, base)]
    return [root / n for root in (_home() / "GitHub", docs) for n in names]


def _first_checkout(env: str, *names: str) -> Path:
    """The engine folder: `env` when it holds an engine, else the first of
    several checkout names that holds one (roots as in _checkout), else
    `env` or the first name's default. The PyBNF fork is PyBNF-pf on the
    development host and PyBNF-Private (its repo name) elsewhere.

    A pin to a folder with no engine is passed over as the launchers pass
    it over: an older Windows setup recorded its default before anything
    was installed, and FluBNF.bat unpacks the lab's archive elsewhere, so
    `flubnf doctor` in a new window looked in an empty folder while fits
    ran from the real one."""
    pinned = _checkout(env, names[0]) if os.environ.get(env) else None
    if pinned is not None and _holds_engine(pinned):
        return pinned
    for c in _engine_search(names):
        if _holds_engine(c):
            return c
    if pinned is not None:
        return pinned
    cands = [_default_checkout(n) for n in names]
    for c in cands:
        if c.exists():
            return c
    return cands[0]


PYBNF = _first_checkout("FLUBNF_PYBNF", "PyBNF-pf", "PyBNF-Private")


# --- Perl, and the environment BNG2.pl runs in -------------------------------
# BNG2.pl is a Perl program. On Windows the first perl on PATH can be one
# that cannot run it: the Unix-style perl of Git's optional Unix tools,
# MSYS2 or Cygwin splits paths on '/' only, so BNG2.pl's own modules are
# not found. And a Strawberry Perl installed after this process started
# (or after the Command Prompt it came from was opened) is not on its PATH.

#: perl path (normcase) -> what `perl -e "print $^O"` printed ('' when it
#: would not run): one subprocess per perl for the life of the process.
#: "unusable" is the first perl the last Windows search passed over, as
#: (path, $^O), or None: what perl_missing_message names.
_PERL = {"os": {}, "unusable": None}

#: the $^O probe's own subprocess.run, bound at import: a test that fakes
#: subprocess.run for BNG2.pl must not answer for perl as well (its
#: answer would be remembered for the session)
_probe = subprocess.run


def _registry_path_dirs() -> list:
    """The machine Path, then the user Path, as the registry holds them
    now, expanded: a process keeps the PATH it started with, and an
    installer writes the registry. [] off Windows or on any failure. A seam
    for tests."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet"
                       r"\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                value, _ = winreg.QueryValueEx(k, "Path")
        except OSError:
            continue
        out += [os.path.expandvars(d) for d in str(value).split(";")]
    return out


#: FluBNF's own Perl on Windows: conda-forge's repack of Strawberry Perl,
#: which FluBNF.bat unpacks under %LOCALAPPDATA%\FluBNF\perl with no
#: administrator (scripts/windows/get_perl.py pins the same file)
OWN_PERL_PACKAGE = "perl-5.32.1.1-2_h57928b3_strawberry.tar.bz2"


def own_perl_dir() -> str | None:
    """The folder of FluBNF's own perl.exe, or None: complete only when
    FluBNF.bat's marker, written after every file was checked, names the
    pinned package."""
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        return None
    root = os.path.join(base, "FluBNF", "perl")
    try:
        with open(os.path.join(root, "flubnf-perl.ok"), encoding="ascii",
                  errors="replace") as f:
            ok = f.readline().strip() == OWN_PERL_PACKAGE
    except OSError:
        return None
    folder = os.path.join(root, "Library", "bin")
    return folder if ok and os.path.isfile(os.path.join(folder, "perl.exe")) \
        else None


def _perl_candidates():
    """Every perl.exe a Windows search may try, in order, each once:
    FluBNF's own (own_perl_dir), as FluBNF.bat checks it first; one per
    folder of this process's PATH, then of the registry's machine and
    user Path, then Strawberry Perl's default folders (the ones setup.ps1
    probes). A generator: the search stops at the first Windows perl, and
    the registry is read only when PATH has none."""
    def folders():
        own = own_perl_dir()
        if own:
            yield own
        for d in os.environ.get("PATH", "").split(os.pathsep):
            yield d
        yield from _registry_path_dirs()
        for base in (os.environ.get("SystemDrive"),
                     os.environ.get("ProgramFiles")):
            if base:
                yield os.path.join(base.rstrip("\\/") + os.sep, "Strawberry",
                                   "perl", "bin")
    seen = set()
    for d in folders():
        d = d.strip().strip('"')
        if not d:
            continue
        f = os.path.join(d, "perl.exe")
        key = os.path.normcase(os.path.abspath(f))
        if key not in seen and os.path.isfile(f):
            seen.add(key)
            yield f


def _perl_os(exe: str) -> str:
    """What `exe -e "print $^O"` prints: MSWin32 for a Windows perl,
    cygwin or msys for the Unix-style ones, '' when it does not run. Asked
    once per perl; a timeout (a first start under a virus scan) is not
    remembered, so the next search asks again."""
    key = os.path.normcase(os.path.abspath(exe))
    if key not in _PERL["os"]:
        try:
            r = _probe([exe, "-e", "print $^O"], capture_output=True,
                       text=True, errors="replace", timeout=30)
            said = r.stdout.strip() if r.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            return ""
        except (OSError, subprocess.SubprocessError, ValueError):
            said = ""
        _PERL["os"][key] = said
    return _PERL["os"][key]


def _first_on(path_value: str, folder: str) -> str:
    """A PATH value with `folder` first (unchanged when it already is)."""
    parts = path_value.split(os.pathsep) if path_value else []
    if parts and (os.path.normcase(parts[0].strip().strip('"'))
                  == os.path.normcase(folder)):
        return path_value
    return os.pathsep.join([folder] + parts)


def resolve_perl(_platform: str | None = None) -> str | None:
    """The perl that runs BNG2.pl, or None.

    macOS and Linux: the first perl on PATH (shutil.which), as always.
    Windows: the first perl.exe whose $^O is MSWin32, looked for in
    FluBNF's own Perl (own_perl_dir), on this process's PATH, then on the
    machine and user Path the registry holds now, then in Strawberry
    Perl's default folders. Its folder is put first
    on this process's PATH, so a bare `perl` (the engine runs one, and
    every child inherits the PATH) is the same perl. The search runs at
    every call and costs one subprocess per perl ever seen, so a Perl
    installed while the console runs is found by the next fit with no
    restart. `_platform` is injectable for tests ("win32": the Windows
    search on any machine)."""
    if not (_platform == "win32" if _platform else _windows()):
        return shutil.which("perl")
    unusable = None
    for exe in _perl_candidates():
        said = _perl_os(exe)
        if said == "MSWin32":
            _PERL["unusable"] = None
            os.environ["PATH"] = _first_on(os.environ.get("PATH", ""),
                                           os.path.dirname(exe))
            return exe
        if unusable is None:
            unusable = (exe, said)
    _PERL["unusable"] = unusable
    return None


def perl_unusable() -> tuple | None:
    """(path, $^O) of the perl the last Windows search found and passed
    over because it is not a Windows perl, when that search found none
    that is; else None."""
    return _PERL["unusable"]


# Here, not in app/core/engines/pf.py (which re-exports both): bng_env needs
# them, and pf imports bng_env from this module.

def _short_path_win(path: str, _api=None):
    """The 8.3 short form of an EXISTING path via GetShortPathNameW (first
    call sizes the buffer), or None on any failure. `_api` is injectable so
    this is testable off Windows."""
    try:
        import ctypes
        if _api is None:
            _api = ctypes.windll.kernel32.GetShortPathNameW   # type: ignore[attr-defined]
        n = _api(path, None, 0)
        if not n:
            return None
        buf = ctypes.create_unicode_buffer(int(n))
        # ret >= n means the path changed between calls: buffer undefined
        ret = _api(path, buf, int(n))
        if not (0 < ret < int(n)):
            return None
        return buf.value or None
    except Exception:
        return None


def perl_path(p, _platform: str | None = None, _api=None,
              _codec: str = "mbcs") -> str | None:
    """`p` as Windows Perl can read it on its command line, or None.

    Strawberry perl.exe takes its arguments in the ANSI code page, so a
    path with letters outside it (Łukasz or 李明 on an English Windows)
    reaches Perl as other letters or '?' and BNG2.pl is never opened. The
    long form when it encodes (Python's mbcs codec refuses an unmappable
    letter), else its 8.3 short form when that encodes, else None. Other
    platforms: str(p). `_platform`, `_api` (GetShortPathNameW) and
    `_codec` are injectable for tests."""
    s = str(p)
    if (_platform or sys.platform) != "win32":
        return s
    try:
        s.encode(_codec)
        return s
    except UnicodeError:
        pass
    short = _short_path_win(s, _api)
    try:
        if short:
            short.encode(_codec)
            return short
    except UnicodeError:
        pass
    return None


def bng_env(bng=None, cwd=None, _platform: str | None = None, _api=None,
            _codec: str = "mbcs") -> dict | None:
    """The environment for a BNG2.pl run, and for an engine runner, which
    runs BNG2.pl itself: this process's, with BNGPATH set to the folder
    BNG2.pl really is in, and on Windows the resolved perl's folder first
    on PATH. None (inherit unchanged) when there is nothing to set.

    BNG2.pl takes its modules (Perl2) and run_network from $BNGPATH
    whenever the variable exists, with no fallback to its own folder, so a
    BNGPATH left by an earlier BioNetGen or PyBNF install (PyBNF's Windows
    docs say `setx BNGPATH ...`) kills every run at compile time once that
    folder is gone. BNGPATH outranks BioNetGenRoot in BNG2.pl and BNGUtils,
    so pinning it is enough. `bng` defaults to BNG; only an existing file
    is pinned (the bare "BNG2.pl" fallback names no folder). On macOS and
    Linux the resolved perl is PATH's own first one, so PATH is left as is.

    `cwd` is the folder BNG2.pl runs in. On Windows a pinned folder holding
    an apostrophe (C:\\Users\\O'Brien) is given relative to it when that
    path is free of quotes: BNG2.pl starts run_network.exe by its path
    under BNGPATH, unquoted when it has no space, and Cygwin's command-line
    parser reads the ' as an opening quote, so run_network gets no
    arguments.

    Windows Perl builds %ENV in the ANSI code page, as it reads its
    arguments, so a BNGPATH with letters outside it (Łukasz or 李明 on an
    English Windows) names a folder that does not exist and BNG2.pl dies
    before its banner, on a path no reinstall changes. Such a BNGPATH is
    given in its 8.3 short form when that fits (perl_path's rule); with
    none, the long one stays pinned, since the preflight refuses that
    folder anyway (perl_path is None) and a BNGPATH left by an earlier
    install must not decide instead. `_platform`, `_api` and `_codec` are
    injectable for tests, as for perl_path."""
    windows = _platform == "win32" if _platform else _windows()
    perl = resolve_perl(_platform) if windows else None   # may update PATH first
    b = str(BNG if bng is None else bng)
    env = None
    if os.path.isfile(b):
        real = os.path.dirname(os.path.realpath(b))
        root = real
        if cwd is not None and "'" in root and windows:
            try:
                rel = os.path.relpath(root, os.path.realpath(str(cwd)))
            except ValueError:                 # another drive: keep it whole
                rel = root
            if "'" not in rel and '"' not in rel:
                root = rel
        if windows and not root.isascii():
            try:
                root.encode(_codec)
            except UnicodeError:
                # the folder itself, as realpath gave it: a short form of
                # the relative one would be read from this process's cwd
                root = perl_path(real, "win32", _api, _codec) or root
        env = dict(os.environ, BNGPATH=root)
    if perl:
        env = dict(os.environ) if env is None else env
        env["PATH"] = _first_on(env.get("PATH", ""), os.path.dirname(perl))
        own = own_perl_dir()
        if own and (os.path.normcase(os.path.dirname(perl))
                    == os.path.normcase(own)):
            # another Perl's module folders or options would go in front
            for var in ("PERL5LIB", "PERLLIB", "PERL5OPT"):
                env.pop(var, None)
    return env


def check(verbose: bool = True) -> list:
    """Return missing externals (empty: this machine can run everything).
    Called by the console and setup.sh.

    The hub is tested by its DATA: a hand-made `git clone --sparse` is a
    valid checkout holding no vintages, and HUB.exists() then reported
    "ready". `auxiliary-data` holds both the archive and locations.csv.
    """
    hub_why = "FluSight hub clone (truth vintages, locations)"
    if HUB.exists():
        hub_why = ("FluSight hub data (truth vintages, locations): the clone "
                   "is present but its sparse checkout does not include the "
                   "data directories")
    # The fork is tested by its pf.py: without it the runner silently
    # imports the engine venv's stock PyBNF and every fit fails.
    pybnf_why = "PyBNF fork with fit_type=pf"
    if PYBNF.exists():
        pybnf_why = ("PyBNF fork with fit_type=pf: the checkout is present "
                     "but holds no pybnf/pf.py, so the fit runner would "
                     "import the stock PyBNF from the engine venv, which "
                     "has no particle filter, and every fit would fail")
    # not a variable: BNG2.pl needs perl, as the fit preflight finds it
    # (resolve_perl; on Windows a native one, such as Strawberry Perl)
    perl = resolve_perl()
    perl_why = "Perl interpreter on PATH (runs BNG2.pl at run preparation)"
    passed = perl_unusable() if perl is None else None
    if passed:
        perl_why = (f"a Windows Perl, FluBNF's own or Strawberry Perl (runs "
                    f"BNG2.pl at run preparation): {passed[0]} is not one")
    missing = []
    for name, p, why in (
        ("FLUBNF_HUB", HUB / "auxiliary-data", hub_why),
        ("FLUBNF_BNG", Path(BNG), "BioNetGen BNG2.pl (network generation)"),
        ("perl", Path(perl or "perl"), perl_why),
        ("FLUBNF_PY_ENGINE", PY_ENGINE, "engine venv python (pybnf + bngsim)"),
        ("FLUBNF_PYBNF", PYBNF / "pybnf" / "pf.py", pybnf_why),
    ):
        if not p.exists():
            missing.append((name, str(p), why))
            if verbose:
                print(f"  MISSING {name}: {p}  ({why})")
    return missing


def load_locations():
    """The locations table from the hub, else the packaged copy, so UI pages
    do not 500 while the hub clone is missing or still fetching."""
    import pandas as pd
    packaged = Path(__file__).resolve().parent / "data/locations.csv"
    last = None
    for src in (LOCATIONS, packaged):
        try:
            return pd.read_csv(src, dtype=str)
        except Exception as e:
            last = e
    raise FileNotFoundError(
        f"no locations table: neither {LOCATIONS} nor {packaged} is readable"
    ) from last
