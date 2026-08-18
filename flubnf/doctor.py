"""Environment + workspace diagnostics.

`flubnf doctor` runs a battery of cheap, non-destructive checks and prints
a pass/warn/fail report. The goal is to catch the half-dozen common
failure modes (stale venv, missing BNG2.pl, broken NumPy 2.0 / pybnf
combination, CDC schema drift, missing templates, unwritable workspace)
*before* the user kicks off a weekly job that would otherwise blow up
midway.

This is run-everywhere, never-destructive code. Network calls are off by
default and gated behind `--online`.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional


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
    # (import_name, friendly_name)
    ("numpy", "numpy"),
    ("pandas", "pandas"),
    ("scipy", "scipy"),
    ("yaml", "pyyaml"),
    ("pydantic", "pydantic"),
    ("typer", "typer"),
    ("rich", "rich"),
    ("requests", "requests"),
    ("pymmwr", "pymmwr"),
)

# pybnf/bngsim live in the ENGINE venv, never this one (two-venv architecture:
# the analysis and engine environments must not import each other's world).
# The doctor probes them where they actually live.


def _check_engine_venv() -> "CheckResult":
    import subprocess
    from flubnf.settings import PY_ENGINE
    if not PY_ENGINE.exists():
        return CheckResult("engine venv", Status.FAIL,
                           f"{PY_ENGINE} missing (set FLUBNF_PY_ENGINE)")
    r = subprocess.run([str(PY_ENGINE), "-c",
                        "import pybnf, bngsim; print(bngsim.__version__)"],
                       capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return CheckResult("engine venv", Status.FAIL,
                           f"pybnf/bngsim not importable: {r.stderr[-120:]}")
    return CheckResult("engine venv", Status.OK,
                       f"bngsim {r.stdout.strip()}")


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
    try:
        import pybnf  # noqa: F401
    except Exception:
        return CheckResult(
            "pybnf NumPy 2.0 patch", Status.FAIL,
            "pybnf not importable; cannot verify patch",
            "pip install pybnf, then re-run doctor.",
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
    # Locate pybnf.algorithms and grep its source for np.Inf occurrences.
    try:
        from pybnf import algorithms as _alg
        src = Path(_alg.__file__).read_text(encoding="utf-8", errors="ignore")
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


def _check_bng(config) -> CheckResult:
    from flubnf.settings import BNG as _BNG
    bng_cmd = Path(config.pybnf.bng_command or _BNG)
    if bng_cmd.exists():
        return CheckResult(
            "BNG2.pl", Status.OK, str(bng_cmd),
        )
    # Try fallback discovery via bionetgen package.
    try:
        import bionetgen
        bng_pkg_dir = Path(bionetgen.__file__).parent / "bng-mac"
        candidate = bng_pkg_dir / "BNG2.pl"
        if candidate.exists():
            return CheckResult(
                "BNG2.pl", Status.WARN,
                f"configured path missing; found at {candidate}",
                f"Set pybnf.bng_command to {candidate} in config.",
            )
    except Exception:
        pass
    return CheckResult(
        "BNG2.pl", Status.FAIL,
        f"not found at {bng_cmd}",
        "Install bionetgen (`pip install bionetgen`) and update "
        "pybnf.bng_command in config to point at BNG2.pl.",
    )


def _check_templates(config) -> list[CheckResult]:
    out: list[CheckResult] = []
    for label, p in [("template_bngl", config.template_bngl),
                     ("template_conf", config.template_conf),
                     ("locations_csv", config.locations_csv)]:
        if Path(p).exists():
            out.append(CheckResult(label, Status.OK, str(p)))
        else:
            out.append(CheckResult(
                label, Status.FAIL, f"missing: {p}",
                "Either restore the file or update the path in your "
                "config YAML.",
            ))
    return out


def _check_workspace(config, workspace_name: Optional[str]) -> list[CheckResult]:
    out: list[CheckResult] = []
    root = config.workspace(workspace_name)
    if not root.exists():
        out.append(CheckResult(
            f"workspace {root.name}", Status.WARN,
            f"does not exist yet ({root})",
            "Run `flubnf init` to create it.",
        ))
        return out
    if not os.access(root, os.W_OK):
        out.append(CheckResult(
            f"workspace {root.name}", Status.FAIL,
            f"not writable: {root}",
            "Check filesystem permissions.",
        ))
        return out
    # Count submissions + sessions
    n_sub = len(list((root / "submissions").glob("*.csv"))) if (
        root / "submissions").exists() else 0
    n_sess = len(list((root / "sessions").glob("*.json"))) if (
        root / "sessions").exists() else 0
    out.append(CheckResult(
        f"workspace {root.name}", Status.OK,
        f"writable; submissions={n_sub} sessions={n_sess}",
    ))
    return out


def _check_data_cache(config) -> CheckResult:
    cache = Path(config.data_cache)
    if not cache.exists():
        return CheckResult(
            "data cache", Status.WARN,
            f"missing: {cache}",
            "Run `flubnf fetch` to populate.",
        )
    csvs = sorted(cache.glob("*.csv"))
    if not csvs:
        return CheckResult(
            "data cache", Status.WARN,
            f"empty: {cache}",
            "Run `flubnf fetch` to populate.",
        )
    latest = csvs[-1]
    # Verify the latest CSV still parses with expected schema.
    try:
        from .fetch import _check_schema, SchemaChangeError
        _check_schema(latest)
    except SchemaChangeError as e:
        return CheckResult(
            "data cache schema", Status.FAIL,
            f"latest CSV failed schema check: {e}",
            "CDC may have renamed columns; update FluBNFConfig.cdc.*_columns.",
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            "data cache schema", Status.WARN, str(e),
        )
    size_mb = latest.stat().st_size / (1024 * 1024)
    return CheckResult(
        "data cache", Status.OK,
        f"{len(csvs)} cached CSV(s); latest={latest.name} ({size_mb:.1f} MB)",
    )


def _check_historical_priors(repo_root: Path) -> CheckResult:
    hp = repo_root / "data" / "historical_priors"
    if not hp.exists():
        return CheckResult(
            "historical priors", Status.WARN,
            "no priors directory yet",
            "Run `flubnf record-season --state ... --season-year ...` "
            "after a season finishes to seed it.",
        )
    files = list(hp.glob("*.json"))
    return CheckResult(
        "historical priors", Status.OK,
        f"{len(files)} state prior file(s)",
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
            "Plenty for a single week, but consider a clean-cache pass.",
        )
    return CheckResult("disk space", Status.OK, f"{free_gb:.0f} GB free")


# ---------------------------------------------------------------------------
# Pre-studio checks — extra paranoia before kicking off a long Mac Studio run
# ---------------------------------------------------------------------------
def _check_studio_historical_priors_loadable(repo_root: Path) -> list[CheckResult]:
    """Every JSON in data/historical_priors/ must parse and at least
    one season's worth of best/p25/p75 params must be present."""
    import json
    out: list[CheckResult] = []
    hp = repo_root / "data" / "historical_priors"
    if not hp.exists():
        return out   # benign: handled by the standard check
    files = sorted(hp.glob("*.json"))
    if not files:
        return out
    n_ok = 0
    bad: list[tuple[str, str]] = []
    for f in files:
        try:
            d = json.loads(f.read_text())
            seasons = d.get("seasons", [])
            if not seasons:
                bad.append((f.name, "no seasons recorded"))
                continue
            need = {"season_year", "best_params", "p25_params", "p75_params"}
            for s in seasons:
                missing = need - set(s)
                if missing:
                    bad.append((f.name, f"missing keys: {sorted(missing)}"))
                    break
            else:
                n_ok += 1
        except Exception as e:
            bad.append((f.name, f"parse error: {e}"))
    if bad:
        for name, reason in bad:
            out.append(CheckResult(
                f"prior {name}", Status.FAIL, reason,
                "Re-run `flubnf record-season` for this state, or remove the "
                "file if it's corrupted.",
            ))
    out.append(CheckResult(
        "historical priors loadable", Status.OK if not bad else Status.WARN,
        f"{n_ok}/{len(files)} files parsed cleanly",
    ))
    return out


def _check_studio_locations_schema(config) -> CheckResult:
    """The locations CSV must have the columns load_locations expects."""
    import pandas as pd
    p = Path(config.locations_csv)
    if not p.exists():
        return CheckResult(
            "locations schema", Status.FAIL,
            f"locations CSV missing: {p}",
        )
    try:
        df = pd.read_csv(p, dtype={"location": str})
    except Exception as e:
        return CheckResult(
            "locations schema", Status.FAIL, f"unreadable: {e}",
        )
    needed = {"abbreviation", "location", "location_name", "population"}
    missing = needed - set(df.columns)
    if missing:
        return CheckResult(
            "locations schema", Status.FAIL,
            f"missing columns: {sorted(missing)}",
            "Restore the canonical FluSight locations.csv (the schema "
            "load_locations() depends on).",
        )
    if len(df) < 53:
        return CheckResult(
            "locations schema", Status.WARN,
            f"only {len(df)} rows; expected ≥53 (50 states + DC + PR + US)",
        )
    return CheckResult(
        "locations schema", Status.OK,
        f"{len(df)} rows; columns OK",
    )


def _check_studio_state_templates(config, workspace_name: Optional[str]
                                   ) -> CheckResult:
    """Every JURISDICTION must have a .bngl + .conf in the workspace (or
    be materializable from templates)."""
    from .constants import JURISDICTIONS
    root = config.workspace(workspace_name)
    if not root.exists():
        return CheckResult(
            "state templates", Status.WARN,
            f"workspace {root.name} not initialized; cannot enumerate",
            "Run `flubnf init` first; this check is meaningful after init.",
        )
    bngl_dir = root / "model_files"
    conf_dir = root / "conf_files"
    missing: list[str] = []
    for j in JURISDICTIONS:
        if not (bngl_dir / f"{j}.bngl").exists():
            missing.append(f"{j}.bngl")
        if not (conf_dir / f"{j}.conf").exists():
            missing.append(f"{j}.conf")
    if missing:
        sample = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
        return CheckResult(
            "state templates", Status.FAIL,
            f"{len(missing)} files missing ({sample})",
            "Run `flubnf init --force` to (re)materialize templates.",
        )
    return CheckResult(
        "state templates", Status.OK,
        f"all {len(JURISDICTIONS)} jurisdictions have .bngl + .conf",
    )


def _check_studio_fringe_detectors() -> CheckResult:
    """Exercise the registered fringe detectors against known-trigger
    fixtures via the public `evaluate_all` API — catches a regression
    where a detector silently stops firing."""
    import numpy as np
    try:
        from . import fringe_cases as fc
        from .session import StateSession
    except Exception as e:
        return CheckResult(
            "fringe detectors", Status.FAIL,
            f"could not import fringe_cases: {e}",
        )

    # Each fixture: (case_name, observed array, session-or-None).
    # The fixtures are tuned to the current detector heuristics; if a
    # detector's thresholds change, the fixture should be updated alongside.
    fixtures: list[tuple[str, np.ndarray, Optional[StateSession]]] = [
        # Outlier week: prior window has IQR > 0 (slight variation), last
        # value is far outside it.
        ("outlier_week",
         np.array([5., 6., 4., 5., 6., 5., 6., 4., 5., 100.]),
         None),
        # Holiday dip: epi-week 52 of 2025 → 2025-12-27. Last week dropped
        # well below the prior 3-week median.
        ("holiday_reporting_dip",
         np.array([200., 220., 250., 260., 270., 280., 300., 310., 320., 200.]),
         StateSession(state="Test", last_reference_date="2025-12-27")),
    ]

    misses: list[str] = []
    n_ok = 0
    for case_name, obs, sess in fixtures:
        try:
            matches = fc.evaluate_all(obs, sess)
        except Exception as e:
            misses.append(f"{case_name} (raised: {e})")
            continue
        fired = next((m for m in matches
                      if m.case_name == case_name and m.triggered), None)
        if fired is None:
            misses.append(case_name)
        else:
            n_ok += 1
    if misses:
        return CheckResult(
            "fringe detectors", Status.FAIL,
            f"did not fire: {', '.join(misses)}",
            "A detector or its trigger threshold regressed — re-run "
            "tests/test_fringe_cases.py for details.",
        )
    return CheckResult(
        "fringe detectors", Status.OK,
        f"{n_ok}/{len(fixtures)} fixtures fired correctly",
    )


def _check_studio_flusight_target(repo_root: Path) -> CheckResult:
    """The FluSight target CSV should be present and have enough rows
    for backtest + baseline-score to be meaningful."""
    import pandas as pd
    p = repo_root / "data" / "flusight_target" / "target-hospital-admissions.csv"
    if not p.exists():
        return CheckResult(
            "flusight target", Status.WARN,
            f"missing: {p}",
            "Run `flubnf fetch` to populate it.",
        )
    try:
        df = pd.read_csv(p, dtype={"location": str}, nrows=1)
        n_lines = sum(1 for _ in p.open()) - 1
    except Exception as e:
        return CheckResult(
            "flusight target", Status.FAIL,
            f"unreadable: {e}",
        )
    needed = {"date", "location", "value"}
    missing = needed - set(df.columns)
    if missing:
        return CheckResult(
            "flusight target", Status.FAIL,
            f"missing columns: {sorted(missing)}",
        )
    if n_lines < 1000:
        return CheckResult(
            "flusight target", Status.WARN,
            f"only {n_lines} rows; full archive is ~10k+",
            "Re-fetch to get a complete archive.",
        )
    return CheckResult(
        "flusight target", Status.OK,
        f"{n_lines} rows; columns OK",
    )


def _check_studio_submission_validator() -> CheckResult:
    """Confirm the schema validator imports + has the expected entry
    points. Cheap, but catches a refactor mistake before prod."""
    try:
        from . import validate as _validate
    except Exception as e:
        return CheckResult(
            "submission validator", Status.FAIL,
            f"could not import: {e}",
        )
    missing = [n for n in ("validate_submission_df", "validate_submission_csv",
                            "ValidationReport")
               if not hasattr(_validate, n)]
    if missing:
        return CheckResult(
            "submission validator", Status.FAIL,
            f"missing attribute(s): {missing}",
            "Schema gate is broken; do NOT run weekly-job until fixed.",
        )
    return CheckResult("submission validator", Status.OK,
                       "validate_submission_{df,csv} callable")


def _check_studio_bng_executable(config) -> CheckResult:
    """Beyond existence — BNG2.pl must be executable."""
    bng = Path(config.pybnf.bng_command)
    if not bng.exists():
        return CheckResult(
            "BNG2.pl executable", Status.FAIL,
            f"missing: {bng}",
        )
    if not os.access(bng, os.X_OK):
        return CheckResult(
            "BNG2.pl executable", Status.FAIL,
            f"not executable: {bng}",
            "chmod +x the file, or check the path.",
        )
    return CheckResult("BNG2.pl executable", Status.OK, "x bit set")


def _check_cdc_reachable(config) -> CheckResult:
    """Optional network check — only runs in --online mode."""
    import requests
    host = config.cdc.socrata_host
    try:
        r = requests.head(
            f"https://{host}/resource/{config.cdc.socrata_dataset}.csv",
            params={"$limit": 1}, timeout=10.0,
        )
        if r.status_code >= 500:
            return CheckResult(
                "CDC Socrata reachable", Status.WARN,
                f"HTTP {r.status_code} from {host}",
                "Socrata may be having issues; retry later or use "
                "--prefer flusight.",
            )
        return CheckResult(
            "CDC Socrata reachable", Status.OK,
            f"HEAD {host}: {r.status_code}",
        )
    except Exception as e:  # noqa: BLE001
        return CheckResult(
            "CDC Socrata reachable", Status.FAIL,
            f"{type(e).__name__}: {e}",
            "Check network; try --prefer flusight to use GitHub mirror.",
        )


# ---------------------------------------------------------------------------
# Top-level orchestration
# ---------------------------------------------------------------------------
def run_doctor(
    config,
    *,
    workspace: Optional[str] = None,
    online: bool = False,
    pre_studio: bool = False,
    repo_root: Optional[Path] = None,
) -> DoctorReport:
    """Run all checks and return a DoctorReport.

    The reverse of "fail early": we keep going through every check even if
    one fails so the user sees every problem in one pass instead of
    fix-rerun-fix-rerun.

    `pre_studio=True` adds extra checks meaningful before a long Mac Studio
    production run — historical-priors schema, locations.csv schema, every
    state template materialized, fringe detectors firing on fixtures, the
    FluSight target archive populated, the schema validator callable, and
    BNG2.pl marked executable.
    """
    rep = DoctorReport()
    rep.add(_check_python())
    rep.add(_check_platform())
    for c in _check_imports():
        rep.add(c)
    rep.add(_check_numpy2_pybnf())
    rep.add(_check_bng(config))
    for c in _check_templates(config):
        rep.add(c)
    for c in _check_workspace(config, workspace):
        rep.add(c)
    rep.add(_check_data_cache(config))
    if repo_root is None:
        repo_root = Path(config.workspace_root).parent
    rep.add(_check_historical_priors(repo_root))
    rep.add(_check_disk_space(Path(config.workspace_root)))
    if pre_studio:
        for c in _check_studio_historical_priors_loadable(repo_root):
            rep.add(c)
        rep.add(_check_studio_locations_schema(config))
        rep.add(_check_studio_state_templates(config, workspace))
        rep.add(_check_studio_fringe_detectors())
        rep.add(_check_studio_flusight_target(repo_root))
        rep.add(_check_studio_submission_validator())
        rep.add(_check_studio_bng_executable(config))
    if online:
        rep.add(_check_cdc_reachable(config))
    return rep
