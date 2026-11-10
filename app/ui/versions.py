"""Build SHA, restart banner and component versions.

RUNNING_SHA is the commit this process runs (git rev-parse at import).
VERSIONS starts as the last launch's snapshot (or pending markers) and is
only ever updated in place, by _warm_versions on the startup warm thread;
the templates, /api/versions, site_build and the ledger all hold that one
dict. ENGINE_BUILD (the engine's build: the public engine's wheel, or the
private fork's branch and commit) is cached the same way. The snapshot
names the engine it was made under, and a launch under the other engine
discards it. _engine_versions_for_ledger records the engine versions on a
run.
"""
from __future__ import annotations

import os as _os
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
            out["bionetgen"] = vf.read_text(encoding="utf-8").strip()
        elif Path(BNG).exists():
            out["bionetgen"] = "installed"
    except Exception:
        pass
    # Perl: BNG2.pl needs it (without it every location fails at preparation);
    # its version, as the other rows read, not the path it was found at
    import json
    import shutil as _shutil
    import subprocess
    out["perl"] = "not installed"
    try:
        from flubnf.settings import resolve_perl
        perl = resolve_perl() or _shutil.which("perl")
    except Exception:
        perl = _shutil.which("perl")
    if perl:
        out["perl"] = "installed"
        try:
            r = subprocess.run([str(perl), "-e", "print $^V"],
                               capture_output=True, text=True, timeout=15)
            v = (r.stdout or "").strip().lstrip("v")
            if r.returncode == 0 and v:
                out["perl"] = v
        except Exception:
            pass
    out["pybnf"] = out["bngsim"] = "not installed"
    try:
        from flubnf.settings import PY_ENGINE, PYBNF, engine_public
        if engine_public():
            # the public engine's venv, installed by pip: no checkout on
            # sys.path, nothing from the environment (-I)
            from flubnf.settings import py_engine_public
            py, cmd = py_engine_public(), ["-I", "-c", _VERSION_PROBE.replace(
                "sys.path.insert(0, %r)\n", "")]
        else:
            py, cmd = PY_ENGINE, ["-c", _VERSION_PROBE % (str(PYBNF),)]
        if Path(py).exists():
            r = subprocess.run([str(py), *cmd], capture_output=True,
                               text=True, timeout=15)
            out.update(json.loads(r.stdout.strip() or "{}"))
    except Exception:
        pass
    return out


#: unresolved-version marker; pages poll /api/versions while any remains
VERSION_PENDING = "resolving…"

#: the bngsim every engine installer pins, which reproduces the sealed record
BNGSIM_PIN = "0.15.1"

#: last launch's resolved probe, so a restart skips the pending markers;
#: in the state folder, which FLUBNF_STATE_DIR moves (as app/core/runs.py)
_VERSIONS_SNAPSHOT = (Path(_os.environ.get("FLUBNF_STATE_DIR")
                           or Path(__file__).resolve().parents[1] / "state")
                      / "component_versions.json")

_VERSION_KEYS = ("fastapi", "jinja2", "plotly", "pandas", "numpy",
                 "bionetgen", "perl", "pybnf", "bngsim")


def _engine_now() -> str | None:
    """The engine this process runs (settings.engine_choice), or None when
    it cannot be read."""
    try:
        from flubnf.settings import engine_choice
        return engine_choice()
    except Exception:
        return None


def _snapshot_engine(snap: dict) -> str:
    """The engine a snapshot was made under: its "engine", else its build's
    (a snapshot from before the engine was stored names "public" only in
    a public build; any other ran the private engine)."""
    e = snap.get("engine")
    if e in ("public", "private"):
        return e
    b = snap.get("engine_build")
    return ("public" if isinstance(b, dict) and b.get("engine") == "public"
            else "private")


def _snapshot() -> dict:
    """The last launch's snapshot, or {} without one. A snapshot made under
    the other engine is discarded: its engine versions and build are that
    engine's, and the warm probe fills in this one's."""
    import json as _json
    try:
        snap = _json.loads(_VERSIONS_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(snap, dict):
        return {}
    now = _engine_now()
    if now is not None and _snapshot_engine(snap) != now:
        return {}
    return snap


def _versions_initial() -> dict:
    """VERSIONS at import: the persisted snapshot, else pending markers. The
    warm probe updates this dict IN PLACE (templates hold the reference)."""
    out = {k: VERSION_PENDING for k in _VERSION_KEYS}
    out.update({k: str(v) for k, v in _snapshot().items()
                if k in _VERSION_KEYS})
    return out


VERSIONS = _versions_initial()


# === Engine build (the public engine's wheel, or the private fork's
# branch and commit) ===
def _build_initial() -> dict:
    """ENGINE_BUILD at import: the persisted snapshot's, else {} (unknown
    until the warm thread resolves it)."""
    b = _snapshot().get("engine_build")
    return dict(b) if isinstance(b, dict) else {}


#: app.core.engine_build.engine_build() of this machine, cached like
#: VERSIONS (resolved on the warm thread, updated IN PLACE) and refreshed
#: whenever a run records it, so a checkout switched while the console
#: runs shows on the next page
ENGINE_BUILD = _build_initial()


def refresh_engine_build() -> dict:
    """Resolve the engine build now (a few git calls), update ENGINE_BUILD
    in place and return a copy. Never raises."""
    from app.core import engine_build as _eb
    b = _eb.engine_build()
    ENGINE_BUILD.clear()
    ENGINE_BUILD.update(b)
    return dict(b)


def engine_build_view() -> dict:
    """What pages show: {label, warning, fix, production, known, commit,
    engine}; engine is the build's ("public" or "private",
    engine_build.engine_of)."""
    from app.core import engine_build as _eb
    from app.core import engine_update as _eu
    b = dict(ENGINE_BUILD)
    fix = _eb.fix(b)
    if _eb.warning(b):
        # why the launcher's update left it (a branch, edits, no access)
        fix = " ".join(x for x in (_eu.last_note(b), fix) if x)
    return {"label": _eb.label(b), "warning": _eb.warning(b),
            "fix": fix, "production": _eb.is_production(b),
            "known": _eb.known(b), "commit": str(b.get("commit") or ""),
            "engine": _eb.engine_of(b)}


def versions_resolved() -> bool:
    return VERSION_PENDING not in VERSIONS.values()


def _engine_versions_for_ledger(engines: str) -> dict:
    """engine_versions for a new ledger row: {"engines": ...} (the key
    historical rows hold) plus each resolved engine component version.
    Pending/'not installed' are probe states, never recorded as versions.
    The engine build (pybnf_build: branch, commit, local edits) is read
    fresh, so the row names the checkout the run actually used."""
    from app.core import engine_build as _eb
    out = {"engines": engines}
    for key in ("pybnf", "bngsim", "bionetgen"):
        v = VERSIONS.get(key)
        if v and v not in (VERSION_PENDING, "not installed", "installed"):
            out[key] = str(v)
    rec = _eb.record(refresh_engine_build())
    if rec:
        out["pybnf_build"] = rec
    return out


def _warm_versions() -> None:
    """The real probe, off the first-paint path: resolve, update VERSIONS in
    place, persist the snapshot for the next launch, with the engine it was
    made under (a launch under the other engine discards it). Never
    raises."""
    import json as _json
    try:
        engine = _engine_now()
        VERSIONS.update(_component_versions())
        refresh_engine_build()
        _VERSIONS_SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        tmp = _VERSIONS_SNAPSHOT.with_suffix(".json.tmp")
        snap = dict(VERSIONS, engine_build=dict(ENGINE_BUILD))
        if engine:
            snap["engine"] = engine
        tmp.write_text(_json.dumps(snap), encoding="utf-8")
        _os.replace(tmp, _VERSIONS_SNAPSHOT)
    except Exception:
        pass
