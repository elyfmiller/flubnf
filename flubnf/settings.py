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
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _path(env: str, *fallbacks: str) -> Path:
    v = os.environ.get(env)
    if v:
        return Path(v).expanduser()
    for f in fallbacks:
        p = Path(f).expanduser()
        if p.exists():
            return p
    return Path(fallbacks[0]).expanduser()


HUB = _path("FLUBNF_HUB", "~/Documents/GitHub/FluSight-forecast-hub")
ARCHIVE = HUB / "auxiliary-data/target-data-archive"
LOCATIONS = HUB / "auxiliary-data/locations.csv"

BNG = _path(
    "FLUBNF_BNG",
    "/opt/anaconda3/lib/python3.12/site-packages/bionetgen/bng-mac/BNG2.pl",
    "/opt/anaconda3/lib/python3.12/site-packages/bionetgen/bng-linux/BNG2.pl",
    shutil.which("BNG2.pl") or "BNG2.pl",
)

PY_ENGINE = _path("FLUBNF_PY_ENGINE", "~/.venvs/flubnf/bin/python")
PYBNF = _path("FLUBNF_PYBNF", "~/Documents/GitHub/PyBNF-pf")


def check(verbose: bool = True) -> list:
    """Return missing externals; the app's doctor command and README both
    point here. An empty list means this machine can run everything."""
    missing = []
    for name, p, why in (
        ("FLUBNF_HUB", HUB, "FluSight hub clone (truth vintages, locations)"),
        ("FLUBNF_BNG", Path(BNG), "BioNetGen BNG2.pl (network generation)"),
        ("FLUBNF_PY_ENGINE", PY_ENGINE, "engine venv python (pybnf + bngsim)"),
        ("FLUBNF_PYBNF", PYBNF, "PyBNF fork with fit_type=pf"),
    ):
        if not p.exists():
            missing.append((name, str(p), why))
            if verbose:
                print(f"  MISSING {name}: {p}  ({why})")
    return missing
