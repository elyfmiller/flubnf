"""SHIPPED (used by the FluBNF console, app/).

Machine-specific paths, resolved once, overridable by environment.

Everything external that flubnf needs to run lives here so a new machine
configures the system by exporting a handful of variables (or editing a
`.env`-style shell profile) instead of patching source:

    FLUBNF_HUB        path to a clone of cdcepi/FluSight-forecast-hub
    FLUBNF_BNG        path to BioNetGen's BNG2.pl
    FLUBNF_PY_ENGINE  python of the engine venv (pybnf + bngsim installed)
    FLUBNF_PYBNF      checkout of the PyBNF fork providing fit_type=pf

Defaults are conventional locations (~/Documents/GitHub on POSIX; see
_checkout for Windows), so a conventionally laid-out machine needs none.
"""
from __future__ import annotations

import os
import shutil
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
    """Where a git checkout lives when `env` is unset.

    POSIX: ~/Documents/GitHub/<name>. Windows: %LOCALAPPDATA%\\FluBNF\\<name>,
    because Controlled Folder Access (Defender), where enabled, blocks
    git.exe and python.exe from writing under Documents. Microsoft ships it
    off; %LOCALAPPDATA% works either way (never protected, does not roam).
    An existing checkout at the old Documents path still wins; nothing here
    moves a directory (docs/WINDOWS.md).
    """
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    legacy = _home() / "Documents" / "GitHub" / name
    if not _windows() or legacy.exists():
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
    """BNG2.pl from `pip install bionetgen` in this app's .venv, POSIX and
    Windows layouts, then the development host's anaconda. First existing
    path wins, so this platform's bundle leads."""
    minor = sys.version_info[1]
    here = Path(__file__).resolve().parents[1]
    dirs = bng_platform_dirs(platform)
    for venv in (here / ".venv",):
        for sp in (venv / "lib" / f"python3.{minor}" / "site-packages",
                   venv / "Lib" / "site-packages"):
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

# ~/.venvs/flubnf (the development host, where sealed results were made)
# first, then setup_engine.sh's ~/.venvs/flubnf-engine; the Scripts forms
# are the Windows layouts and never exist on POSIX.
PY_ENGINE = _path("FLUBNF_PY_ENGINE", "~/.venvs/flubnf/bin/python",
                  "~/.venvs/flubnf-engine/bin/python",
                  "~/.venvs/flubnf/Scripts/python.exe",
                  "~/.venvs/flubnf-engine/Scripts/python.exe")


def _first_checkout(env: str, *names: str) -> Path:
    """The first of several checkout names that exists (roots as in
    _checkout), else the first name's default. The PyBNF fork is PyBNF-pf
    on the development host and PyBNF-Private (its repo name) elsewhere."""
    if os.environ.get(env):
        return _checkout(env, names[0])
    cands = [_checkout(env, n) for n in names]
    for c in cands:
        if c.exists():
            return c
    return cands[0]


PYBNF = _first_checkout("FLUBNF_PYBNF", "PyBNF-pf", "PyBNF-Private")


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
    missing = []
    for name, p, why in (
        ("FLUBNF_HUB", HUB / "auxiliary-data", hub_why),
        ("FLUBNF_BNG", Path(BNG), "BioNetGen BNG2.pl (network generation)"),
        # not a variable: BNG2.pl needs perl on PATH (Windows: Strawberry)
        ("perl", Path(shutil.which("perl") or "perl"),
         "Perl interpreter on PATH (runs BNG2.pl at run preparation)"),
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
