"""CONSOLE (`flubnf doctor`): environment diagnostics; network checks only with --online.

`flubnf doctor` runs cheap, never-destructive checks (Python, the console's
packages, the engine venv and PyBNF fork, the NumPy 2.0 / pybnf patch, the
FluSight hub clone, BNG2.pl, disk space) and prints a pass/warn/fail report,
so a broken install shows before a long run can blow up midway. It reads no
config: every path comes from flubnf.settings (the FLUBNF_* variables).
"""

from __future__ import annotations

import importlib
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Status(Enum):
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass
class CheckResult:
    name: str
    status: Status
    detail: str = ""
    hint: str = ""

    def short(self) -> str:
        return f"[{self.status.value}] {self.name}: {self.detail}"


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, c: CheckResult) -> None:
        self.checks.append(c)

    @property
    def n_fail(self) -> int:
        return sum(1 for c in self.checks if c.status is Status.FAIL)

    @property
    def n_warn(self) -> int:
        return sum(1 for c in self.checks if c.status is Status.WARN)

    @property
    def healthy(self) -> bool:
        return self.n_fail == 0


# ---------------------------------------------------------------------------
# Check primitives — each returns CheckResult
# ---------------------------------------------------------------------------
def _check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    if (major, minor) < (3, 10):
        return CheckResult(
            "python", Status.FAIL,
            f"{sys.version.split()[0]} — requires 3.10+",
            "Install Python 3.10 or newer and recreate the venv.",
        )
    if (major, minor) >= (3, 13):
        return CheckResult(
            "python", Status.WARN,
            f"{sys.version.split()[0]} — untested above 3.12",
            "CI matrix covers 3.10/3.11/3.12; newer is unverified.",
        )
    return CheckResult("python", Status.OK, sys.version.split()[0])


def _check_platform() -> CheckResult:
    return CheckResult(
        "platform", Status.OK,
        f"{platform.system()} {platform.release()} ({platform.machine()})",
    )


_REQUIRED_PACKAGES: tuple[tuple[str, str], ...] = (
    # (import_name, friendly_name): pyproject's runtime dependencies
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("typer", "typer"),
    ("rich", "rich"),
)

# pybnf/bngsim live in the ENGINE venv (two-venv architecture), so they are
# probed there, with the engine's python, never imported in this (console)
# venv. The engine is optional: without it the console runs Groundhog-only,
# so an ABSENT engine is a WARN; a present engine that cannot import is a
# FAIL.

#: The console's own readiness probe (setup.ps1 / FluBNF.bat): pybnf is
#: loaded off the fork checkout, as the fit runners load it.
ENGINE_PROBE = ("import sys; sys.path.insert(0, {pybnf!r}); import bngsim; "
                "from pybnf.pf import ParticleFilter; print(bngsim.__version__)")

_ENGINE_ABSENT_HINT = ("Optional: without the engine the console runs "
                       "Groundhog-only. To add the particle filter, run "
                       "./setup_engine.sh (or set FLUBNF_PY_ENGINE and "
                       "FLUBNF_PYBNF), then re-run doctor.")


def _check_engine_venv() -> "CheckResult":
    """Whether the engine venv can import what a fit needs, probed exactly
    as the console probes it: the engine python, the fork on sys.path,
    `import bngsim; from pybnf.pf import ParticleFilter`."""
    from flubnf.settings import PY_ENGINE, PYBNF
    if not Path(PY_ENGINE).exists():
        return CheckResult("engine venv", Status.WARN,
                           f"{PY_ENGINE} missing (set FLUBNF_PY_ENGINE)",
                           _ENGINE_ABSENT_HINT)
    try:
        r = subprocess.run([str(PY_ENGINE), "-c",
                            ENGINE_PROBE.format(pybnf=str(PYBNF))],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        return CheckResult("engine venv", Status.FAIL,
                           f"could not run {PY_ENGINE}: {e}")
    if r.returncode != 0:
        return CheckResult("engine venv", Status.FAIL,
                           "bngsim / pybnf.pf not importable in the engine "
                           f"venv: {(r.stderr or '')[-120:]}",
                           "Re-run ./setup_engine.sh, then re-run doctor.")
    return CheckResult("engine venv", Status.OK,
                       f"bngsim {r.stdout.strip()}")


def _check_pf_engine() -> "CheckResult":
    """The PyBNF fork, tested by the file that carries fit_type = pf.

    Not by importing pybnf: stock PyBNF imports fine and cannot filter.
    """
    from app.core.engines import pf as _pf
    from flubnf.settings import PYBNF
    if not _pf.engine_available():
        # no checkout at all: the engine is simply not installed (WARN);
        # a checkout without pf.py is a broken install (FAIL)
        if not Path(_pf.PYBNF_PF).exists():
            return CheckResult("PyBNF fork (fit_type=pf)", Status.WARN,
                               _pf.engine_missing_message(),
                               _ENGINE_ABSENT_HINT)
        return CheckResult("PyBNF fork (fit_type=pf)", Status.FAIL,
                           _pf.engine_missing_message(),
                           "Run ./setup_engine.sh (or set FLUBNF_PYBNF), then "
                           "re-run doctor.")
    if not _pf.engine_current():
        return CheckResult("PyBNF fork (fit_type=pf)", Status.FAIL,
                           _pf.engine_stale_message(),
                           "Save the current engine archive in Downloads and "
                           "run ./setup_engine.sh, then re-run doctor.")
    return CheckResult("PyBNF fork (fit_type=pf)", Status.OK, str(PYBNF))


#: what a usable hub clone must hold (a sparse checkout can lack either)
HUB_DIRS = ("target-data", "auxiliary-data/target-data-archive")


def _check_hub() -> CheckResult:
    """The FluSight hub clone (settings.HUB, FLUBNF_HUB): truth and its
    vintages. Tested by its data directories, not by the clone existing."""
    from flubnf.settings import HUB
    hub = Path(HUB)
    if not hub.is_dir():
        return CheckResult(
            "FluSight hub", Status.FAIL, f"no clone at {hub}",
            "Clone cdcepi/FluSight-forecast-hub there, or set FLUBNF_HUB "
            "to an existing clone.")
    missing = [d for d in HUB_DIRS if not (hub / d).is_dir()]
    if missing:
        return CheckResult(
            "FluSight hub", Status.FAIL,
            f"{hub} lacks {', '.join(missing)}",
            "A sparse checkout must include target-data/ and "
            "auxiliary-data/ (sparse-checkout add target-data "
            "auxiliary-data).")
    return CheckResult("FluSight hub", Status.OK, str(hub))


def _check_imports() -> list[CheckResult]:
    out: list[CheckResult] = []
    for mod, friendly in _REQUIRED_PACKAGES:
        try:
            m = importlib.import_module(mod)
            ver = getattr(m, "__version__", "?")
            out.append(CheckResult(
                f"import {friendly}", Status.OK, ver,
            ))
        except Exception as e:  # noqa: BLE001
            out.append(CheckResult(
                f"import {friendly}", Status.FAIL, str(e),
                f"pip install {friendly}",
            ))
    return out


def _check_numpy2_pybnf() -> CheckResult:
    """The NumPy 2.0 / pybnf incompat patches: np.Inf -> np.inf, and
    `nbinom.rvs(...)` -> `float(nbinom.rvs(..., size=1)[0])` to coerce
    the 0-d / array returns the new SciPy emits.
    """
    # The engine's pybnf, read as a file: the fork checkout the runners put
    # first on sys.path, else a pybnf this venv happens to carry. pybnf is
    # an engine-venv package, so neither being present means the engine is
    # absent (WARN; the console runs Groundhog-only), not a broken install.
    from flubnf.settings import PYBNF
    alg_path = Path(PYBNF) / "pybnf" / "algorithms.py"
    if not alg_path.is_file():
        try:
            from pybnf import algorithms as _alg
            alg_path = Path(_alg.__file__)
        except Exception:
            return CheckResult(
                "pybnf NumPy 2.0 patch", Status.WARN,
                f"no engine pybnf (no {alg_path}); cannot verify patch",
                _ENGINE_ABSENT_HINT,
            )
    try:
        import numpy as _np
        if int(_np.__version__.split(".")[0]) < 2:
            return CheckResult(
                "pybnf NumPy 2.0 patch", Status.OK,
                "numpy<2 — patch unnecessary",
            )
    except Exception:
        pass
    # Grep the engine's pybnf/algorithms.py for np.Inf occurrences.
    try:
        src = alg_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            "pybnf NumPy 2.0 patch", Status.WARN,
            f"could not read pybnf/algorithms.py: {e}",
        )
    if "np.Inf" in src:
        return CheckResult(
            "pybnf NumPy 2.0 patch", Status.FAIL,
            "pybnf/algorithms.py still contains `np.Inf` (broken under "
            "NumPy 2.0)",
            "Run the CI patch script or manually replace np.Inf with np.inf",
        )
    # nbinom patch check
    if "nbinom.rvs(n=self.r, p=self.prob)" in src:
        return CheckResult(
            "pybnf NumPy 2.0 patch", Status.FAIL,
            "pybnf/algorithms.py uses scalar nbinom.rvs (returns 0-d "
            "array under SciPy 1.11+, breaks float assignment)",
            "Wrap with: float(stats.nbinom.rvs(n=..., p=..., size=1)[0])",
        )
    return CheckResult("pybnf NumPy 2.0 patch", Status.OK, "patches applied")


def _check_bng() -> CheckResult:
    """BNG2.pl at settings.BNG (FLUBNF_BNG, else the conventional places)."""
    from flubnf.settings import BNG as _BNG
    bng_cmd = Path(_BNG)
    if bng_cmd.exists():
        return CheckResult(
            "BNG2.pl", Status.OK, str(bng_cmd),
        )
    # Try fallback discovery via bionetgen package.
    # (this platform's bundle first: bng-mac's binaries do not run on Linux)
    try:
        import bionetgen
        from flubnf.settings import bng_platform_dirs
        for plat in bng_platform_dirs():
            candidate = Path(bionetgen.__file__).parent / plat / "BNG2.pl"
            if candidate.exists():
                return CheckResult(
                    "BNG2.pl", Status.WARN,
                    f"configured path missing; found at {candidate}",
                    f"Set FLUBNF_BNG to {candidate}.",
                )
    except Exception:
        pass
    return CheckResult(
        "BNG2.pl", Status.FAIL,
        f"not found at {bng_cmd}",
        "Install bionetgen (`pip install bionetgen`) and set FLUBNF_BNG "
        "to its BNG2.pl.",
    )


def _check_disk_space(path: Path) -> CheckResult:
    try:
        usage = shutil.disk_usage(path)
    except Exception as e:  # noqa: BLE001
        return CheckResult("disk space", Status.WARN, str(e))
    free_gb = usage.free / (1024 ** 3)
    if free_gb < 2.0:
        return CheckResult(
            "disk space", Status.FAIL,
            f"{free_gb:.1f} GB free at {path}",
            "PyBNF runs need a few GB scratch; free up disk.",
        )
    if free_gb < 10.0:
        return CheckResult(
            "disk space", Status.WARN,
            f"{free_gb:.1f} GB free at {path}",
            "Plenty for a single week; the console's Storage page "
            "(/storage) shows what can be cleared.",
        )
    return CheckResult("disk space", Status.OK, f"{free_gb:.0f} GB free")


#: The network services the product reads, probed with --online: the Delphi
#: Epidata API (NREVSS, ILINet and FluSurv, for donor-bank builds and
#: verification) and GitHub (where setup clones the FluSight hub and the
#: console pulls it).
ONLINE_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("Delphi Epidata reachable", "https://api.delphi.cmu.edu/epidata/"),
    ("GitHub reachable", "https://github.com/cdcepi/FluSight-forecast-hub"),
)


def _check_reachable(name: str, url: str) -> CheckResult:
    """Optional network check — only runs in --online mode. Any HTTP answer
    below 500 means the host is reachable; 5xx is a WARN (the service is
    having trouble), no answer at all a FAIL."""
    import urllib.error
    import urllib.parse
    import urllib.request
    host = urllib.parse.urlsplit(url).netloc
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "flubnf-doctor"})
    try:
        with urllib.request.urlopen(req, timeout=10.0) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            name, Status.FAIL, f"{type(e).__name__}: {e}",
            "Check the network connection.",
        )
    if code >= 500:
        return CheckResult(
            name, Status.WARN, f"HTTP {code} from {host}",
            f"{host} may be having issues; retry later.",
        )
    return CheckResult(name, Status.OK, f"HEAD {host}: {code}")


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------
def _disk_path() -> Path:
    """Where the console writes: app/state when it exists, else the repo."""
    repo = Path(__file__).resolve().parents[1]
    state = repo / "app" / "state"
    return state if state.is_dir() else repo


def run_doctor(*, online: bool = False) -> DoctorReport:
    """Run all checks and return a DoctorReport.

    Every check runs even after a failure, so all problems show in one pass.
    `online=True` adds the network checks (ONLINE_ENDPOINTS).
    """
    rep = DoctorReport()
    rep.add(_check_python())
    rep.add(_check_platform())
    for c in _check_imports():
        rep.add(c)
    rep.add(_check_numpy2_pybnf())
    rep.add(_check_engine_venv())        # can the engine venv import at all
    rep.add(_check_pf_engine())          # and does the fork carry pf.py
    rep.add(_check_hub())                # truth + vintages for scoring
    rep.add(_check_bng())
    rep.add(_check_disk_space(_disk_path()))
    if online:
        for name, url in ONLINE_ENDPOINTS:
            rep.add(_check_reachable(name, url))
    return rep
