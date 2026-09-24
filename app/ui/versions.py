"""Build SHA, restart banner and component versions.

RUNNING_SHA is the commit this process runs (git rev-parse at import).
VERSIONS starts as the last launch's snapshot (or pending markers) and is
only ever updated in place, by _warm_versions on the startup warm thread;
the templates, /api/versions, site_build and the ledger all hold that one
dict. _engine_versions_for_ledger records the engine versions on a run.
"""
from __future__ import annotations

from pathlib import Path

from app.core import ttlcache


# === Build SHA and restart banner ===
def _repo_sha(short: bool = True) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "--short" if short else "HEAD",
                            "HEAD"], capture_output=True, text=True, timeout=5,
                           cwd=str(Path(__file__).resolve().parents[2]))
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


RUNNING_SHA = _repo_sha()   # the code THIS process actually executes


@ttlcache.ttl_cache(ttl_s=10.0)
def _repo_sha_on_disk() -> str:
    """Cached HEAD (10 s): the restart banner reads it on every render, and
    a git subprocess per page (~20 ms) was the largest fixed render cost."""
    return _repo_sha()


def _restart_needed() -> bool:
    """True when a pull landed but this process still runs the old build
    (templates and static files reload; server logic does not)."""
    sha = _repo_sha_on_disk()
    return bool(sha and RUNNING_SHA and sha != RUNNING_SHA)


# === Component versions ===
#: pybnf/bngsim probe run by the engine venv's interpreter. Like the generated
#: runners (pf.py _RUNNER, retro.py _RETRO_RUNNER) it puts the PyBNF checkout
#: first on sys.path, and reads __version__ from the imported pybnf.py (the
#: fork runs from a checkout, not pip); importlib.metadata is the fallback.
_VERSION_PROBE = '''
import json, os, re, sys
sys.path.insert(0, %r)
from importlib.metadata import version
d = {}
for p in ("pybnf", "bngsim"):
    try:
        d[p] = version(p)
    except Exception:
        d[p] = "not installed"
try:
    import pybnf
    src = open(os.path.join(os.path.dirname(pybnf.__file__), "pybnf.py")).read()
    m = re.search(r'^__version__\\s*=\\s*"(.*)"', src, re.M)
    if m:
        d["pybnf"] = m.group(1)
except Exception:
    pass
print(json.dumps(d))
'''


def _component_versions() -> dict:
    """Versions of the components named in user-facing copy: console
    packages via importlib.metadata, pybnf/bngsim via _VERSION_PROBE,
    BioNetGen from the VERSION file beside BNG2.pl; 'not installed' when
    unresolvable.

    Slow (~1 s, engine-venv subprocess): never call at import. _warm_versions
    runs it on the warm thread; until then VERSIONS serves the persisted
    snapshot or pending markers, and pages fill in via /api/versions."""
    from importlib.metadata import PackageNotFoundError, version
    out = {}
    for pkg in ("fastapi", "jinja2", "plotly", "pandas", "numpy"):
        try:
            out[pkg] = version(pkg)
        except PackageNotFoundError:
            out[pkg] = "not installed"
    out["bionetgen"] = "not installed"
    try:
        from flubnf.settings import BNG
        vf = Path(BNG).parent / "VERSION"
        if vf.is_file():
            out["bionetgen"] = vf.read_text().strip()
        elif Path(BNG).exists():
            out["bionetgen"] = "installed"
    except Exception:
        pass
    # Perl: BNG2.pl needs it (without it every location fails at preparation)
    import shutil as _shutil
    out["perl"] = _shutil.which("perl") or "not installed"
    out["pybnf"] = out["bngsim"] = "not installed"
    try:
        import json
        import subprocess
        from flubnf.settings import PY_ENGINE, PYBNF
        if Path(PY_ENGINE).exists():
            r = subprocess.run(
                [str(PY_ENGINE), "-c", _VERSION_PROBE % (str(PYBNF),)],
                capture_output=True, text=True, timeout=15)
            out.update(json.loads(r.stdout.strip() or "{}"))
    except Exception:
        pass
    return out


#: unresolved-version marker; pages poll /api/versions while any remains
VERSION_PENDING = "resolving…"

#: last launch's resolved probe, so a restart skips the pending markers
_VERSIONS_SNAPSHOT = (Path(__file__).resolve().parents[1]
                      / "state" / "component_versions.json")

_VERSION_KEYS = ("fastapi", "jinja2", "plotly", "pandas", "numpy",
                 "bionetgen", "perl", "pybnf", "bngsim")


def _versions_initial() -> dict:
    """VERSIONS at import: the persisted snapshot, else pending markers. The
    warm probe updates this dict IN PLACE (templates hold the reference)."""
    import json as _json
    out = {k: VERSION_PENDING for k in _VERSION_KEYS}
    try:
        snap = _json.loads(_VERSIONS_SNAPSHOT.read_text())
        if isinstance(snap, dict):
            out.update({k: str(v) for k, v in snap.items()
                        if k in _VERSION_KEYS})
    except Exception:
        pass
    return out


VERSIONS = _versions_initial()


def versions_resolved() -> bool:
    return VERSION_PENDING not in VERSIONS.values()


def _engine_versions_for_ledger(engines: str) -> dict:
    """engine_versions for a new ledger row: {"engines": ...} (the key
    historical rows hold) plus each resolved engine component version.
    Pending/'not installed' are probe states, never recorded as versions."""
    out = {"engines": engines}
    for key in ("pybnf", "bngsim", "bionetgen"):
        v = VERSIONS.get(key)
        if v and v not in (VERSION_PENDING, "not installed", "installed"):
            out[key] = str(v)
    return out


def _warm_versions() -> None:
    """The real probe, off the first-paint path: resolve, update VERSIONS in
    place, persist the snapshot for the next launch. Never raises."""
    import json as _json
    try:
        VERSIONS.update(_component_versions())
        _VERSIONS_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _VERSIONS_SNAPSHOT.with_suffix(".json.tmp")
        tmp.write_text(_json.dumps(VERSIONS))
        import os as _os
        _os.replace(tmp, _VERSIONS_SNAPSHOT)
    except Exception:
        pass
