"""Machine-specific paths, resolved once, overridable by environment.

Everything external that flubnf needs to run lives here so a new machine
configures the system by exporting a handful of variables (or editing a
`.env`-style shell profile) instead of patching source:

    FLUBNF_HUB        path to a clone of cdcepi/FluSight-forecast-hub
    FLUBNF_BNG        path to BioNetGen's BNG2.pl
    FLUBNF_PY_ENGINE  python of the engine venv (pybnf + bngsim installed)
    FLUBNF_PYBNF      checkout of the PyBNF fork providing fit_type=pf

Defaults fall back to conventional locations under ~/Documents/GitHub so a
machine laid out like the development host needs no configuration at all.
On Windows the checkout defaults move out of Documents; see _checkout below.
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def _windows() -> bool:
    """Is this a Windows machine?

    A named function so a test can exercise the Windows branch of _checkout
    from a Mac. Faking `os.name` instead would work and would also turn
    every pathlib.Path created afterwards into a WindowsPath, which is not
    something a test may do to the rest of the process.
    """
    return sys.platform.startswith("win")


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
    """Where a git checkout lives when the environment says nothing.

    POSIX is unchanged: ~/Documents/GitHub/<name>, the layout of the
    development host and of every macOS and Linux setup script.

    Windows moves the default to %LOCALAPPDATA%\\FluBNF\\<name>, because
    Controlled Folder Access -- Microsoft Defender's ransomware protection
    -- protects Documents and lets only trusted programs write there.
    git.exe and python.exe are not trusted out of the box, so a checkout
    under Documents is one git.exe cannot clone or pull into and one
    python.exe cannot write __pycache__ inside. Both were recorded on the
    corresponding author's machine on 2026-08-25, Defender event 1123.

    Microsoft ships the protection OFF; that machine had it on, whether by
    the user, the image, or IT policy. The default is chosen so the answer
    does not matter: %LOCALAPPDATA% is the documented per-user application
    data location, is never in the protected set, and does not roam.

    An existing checkout at the old Documents path still wins, so a machine
    configured before this change keeps working untouched. Nothing here ever
    moves a directory; see docs/WINDOWS.md.
    """
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    legacy = Path("~/Documents/GitHub").expanduser() / name
    if not _windows() or legacy.exists():
        return legacy
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path("~/AppData/Local").expanduser()
    return base / "FluBNF" / name


HUB = _checkout("FLUBNF_HUB", "FluSight-forecast-hub")
ARCHIVE = HUB / "auxiliary-data/target-data-archive"
LOCATIONS = HUB / "auxiliary-data/locations.csv"

def _bng_candidates():
    """BNG2.pl from `pip install bionetgen`, wherever this app's venv lives --
    the resolution a fresh lab machine actually needs. Covers the POSIX venv
    layout (lib/pythonX.Y/site-packages) and the Windows one
    (Lib/site-packages); the platform order keeps bng-mac winning on macOS
    (candidates are tried in order, first existing path wins)."""
    minor = __import__("sys").version_info[1]
    here = Path(__file__).resolve().parents[1]
    for venv in (here / ".venv",):
        for sp in (venv / "lib" / f"python3.{minor}" / "site-packages",
                   venv / "Lib" / "site-packages"):
            for plat in ("bng-mac", "bng-linux", "bng-win"):
                yield str(sp / "bionetgen" / plat / "BNG2.pl")


BNG = _path(
    "FLUBNF_BNG",
    *_bng_candidates(),
    "/opt/anaconda3/lib/python3.12/site-packages/bionetgen/bng-mac/BNG2.pl",
    "/opt/anaconda3/lib/python3.12/site-packages/bionetgen/bng-linux/BNG2.pl",
    shutil.which("BNG2.pl") or "BNG2.pl",
)

# The Scripts variants are the same venvs as Windows lays them out; on
# POSIX they never exist, so the earlier fallbacks keep winning there.
# ~/.venvs/flubnf is the development host's venv and stays first so the
# sealed results keep reproducing against the exact interpreter that made
# them; ~/.venvs/flubnf-engine is what setup_engine.sh creates on every
# other machine (field report 2026-08-26: a laptop with a verified engine
# reported "not installed" because this list knew only the dev host's
# layout and left .flubnf.env as the single point of failure).
PY_ENGINE = _path("FLUBNF_PY_ENGINE", "~/.venvs/flubnf/bin/python",
                  "~/.venvs/flubnf-engine/bin/python",
                  "~/.venvs/flubnf/Scripts/python.exe",
                  "~/.venvs/flubnf-engine/Scripts/python.exe")


def _first_checkout(env: str, *names: str) -> Path:
    """The first of several checkout names that exists on disk, under the
    same per-platform roots as _checkout; the first name's default when
    none exists yet. PyBNF needs this because the fork lives as PyBNF-pf
    on the development host but clones as PyBNF-Private (the repository's
    actual name, and what GitHub Desktop names it) everywhere else."""
    if os.environ.get(env):
        return _checkout(env, names[0])
    cands = [_checkout(env, n) for n in names]
    for c in cands:
        if c.exists():
            return c
    return cands[0]


PYBNF = _first_checkout("FLUBNF_PYBNF", "PyBNF-pf", "PyBNF-Private")


def check(verbose: bool = True) -> list:
    """Return missing externals; the app's doctor command and README both
    point here. An empty list means this machine can run everything.

    The hub is tested by its DATA, not by the directory. `git clone --sparse`
    checks out the repository root and nothing else, so a hub cloned by hand
    is a directory that exists, is a valid git checkout, and contains no
    truth vintages whatsoever. Testing `HUB.exists()` printed "all externals
    present -- you are ready" over exactly that state (field report,
    2026-08-25), which is worse than saying nothing. `auxiliary-data` is the
    first sparse directory the app reads and holds both the vintage archive
    and locations.csv, so its absence is the honest signal.
    """
    hub_why = "FluSight hub clone (truth vintages, locations)"
    if HUB.exists():
        hub_why = ("FluSight hub data (truth vintages, locations): the clone "
                   "is present but its sparse checkout does not include the "
                   "data directories")
    missing = []
    for name, p, why in (
        ("FLUBNF_HUB", HUB / "auxiliary-data", hub_why),
        ("FLUBNF_BNG", Path(BNG), "BioNetGen BNG2.pl (network generation)"),
        ("FLUBNF_PY_ENGINE", PY_ENGINE, "engine venv python (pybnf + bngsim)"),
        ("FLUBNF_PYBNF", PYBNF, "PyBNF fork with fit_type=pf"),
    ):
        if not p.exists():
            missing.append((name, str(p), why))
            if verbose:
                print(f"  MISSING {name}: {p}  ({why})")
    return missing


def load_locations(dtype=str):
    """The locations table, from the hub when present and from the packaged
    copy otherwise. Every UI read goes through this: a page that only needs
    names, abbreviations, and populations must not 500 on a machine whose
    hub clone is missing or still fetching (CI and fresh laptops both hit
    this, twice)."""
    import pandas as pd
    packaged = Path(__file__).resolve().parent / "data/locations.csv"
    last = None
    for src in (LOCATIONS, packaged):
        try:
            return pd.read_csv(src, dtype=dtype)
        except Exception as e:
            last = e
    raise FileNotFoundError(
        f"no locations table: neither {LOCATIONS} nor {packaged} is readable"
    ) from last
