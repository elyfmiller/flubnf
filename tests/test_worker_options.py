"""Run options must reach pool workers. They did not, and nothing said so.

THE BUG THIS EXISTS TO PREVENT
------------------------------
`vintage_run` and `rt_prior_run` set module-level globals in `main()` and read
them inside the function submitted to `ProcessPoolExecutor`:

    OPTS = {"min_model": False, "window_weeks": None}   # "so pool workers inherit"
    ...
    def main():
        OPTS["window_weeks"] = a.window_weeks           # never seen by a worker

That comment is true on Linux, where multiprocessing forks. **macOS spawns.** A
spawned worker RE-IMPORTS the module, so every such global reverts to the value
in the source file and the command-line flag is silently ignored.

The cost was not theoretical. Three "rolling window" arms -- 8 weeks, 12 weeks,
full season, 312 PyBNF fits over ~19 hours -- were three identical full-season
runs. Their `season_start_used` fields are all `2025-08-01`. A 4.8% "window
effect" was reported, defended, and built into a recommendation before anyone
noticed. The same bug made `--min-model` a no-op, so a campaign labelled
"5-parameter" fitted the 8-parameter model.

Nothing failed. No exception, no warning, no log line. The only evidence was a
field in the output that nobody read.

WHAT THESE TESTS CHECK
----------------------
1. That spawn really does drop module state, so the premise stays documented
   even if someone later "simplifies" the args tuple back to a global.
2. That the args tuple each runner builds matches what its worker unpacks --
   a length mismatch is the cheap, deterministic proxy for "an option was
   dropped on the way to the worker".
3. That the option actually changes the artefact it is supposed to change.
"""
from __future__ import annotations

import ast
import inspect
import multiprocessing as mp
import re
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


# --------------------------------------------------------------------------
# 1. the platform premise
# --------------------------------------------------------------------------
def _worker_reads_global(_):
    import tests.helpers_spawn as h
    return h.FLAG[0]


class TestSpawnDropsModuleState:
    def test_start_method_is_spawn_on_macos(self):
        """If this ever becomes 'fork', the original code would have worked --
        and the args-tuple plumbing becomes belt-and-braces rather than load
        bearing. Either way the fact should be asserted, not assumed."""
        if sys.platform == "darwin":
            assert mp.get_start_method() == "spawn"

    @pytest.mark.skipif(sys.platform != "darwin", reason="spawn-specific")
    def test_a_global_set_in_the_parent_is_not_seen_by_a_worker(self, tmp_path):
        helpers = ROOT / "tests" / "helpers_spawn.py"
        helpers.write_text("FLAG = ['DEFAULT']\n")
        try:
            import tests.helpers_spawn as h
            h.FLAG[0] = "SET-IN-PARENT"
            assert h.FLAG[0] == "SET-IN-PARENT"
            with ProcessPoolExecutor(max_workers=1) as ex:
                seen = list(ex.map(_worker_reads_global, [0]))[0]
            assert seen == "DEFAULT", (
                "spawn no longer drops module state; revisit the args-tuple "
                "plumbing in vintage_run/rt_prior_run")
        finally:
            helpers.unlink(missing_ok=True)


# --------------------------------------------------------------------------
# 2. every runner's job tuple must match its worker's unpacking
# --------------------------------------------------------------------------
def _tuple_len_in_jobs(src: str) -> int | None:
    """Length of the tuple literal in `jobs = [( ... ) for ...]`."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and node.targets
                and getattr(node.targets[0], "id", None) == "jobs"
                and isinstance(node.value, ast.ListComp)
                and isinstance(node.value.elt, ast.Tuple)):
            return len(node.value.elt.elts)
    return None


def _unpack_len_in_one_fit(src: str) -> int | None:
    """Number of names the worker unpacks from `args`."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "one_fit":
            for stmt in ast.walk(node):
                if (isinstance(stmt, ast.Assign)
                        and isinstance(stmt.value, ast.Name)
                        and stmt.value.id == "args"
                        and isinstance(stmt.targets[0], ast.Tuple)):
                    return len(stmt.targets[0].elts)
    return None


@pytest.mark.parametrize("script", ["vintage_run.py", "rt_prior_run.py"])
class TestJobTupleMatchesWorker:
    def test_lengths_agree(self, script):
        src = (SCRIPTS / script).read_text()
        built, unpacked = _tuple_len_in_jobs(src), _unpack_len_in_one_fit(src)
        assert built is not None, f"{script}: no `jobs = [(...)]` found"
        assert unpacked is not None, f"{script}: one_fit does not unpack args"
        assert built == unpacked, (
            f"{script}: main() builds a {built}-tuple but one_fit unpacks "
            f"{unpacked}. An option is being dropped between them.")

    def test_worker_does_not_read_run_options_from_module_state(self, script):
        """The specific regression: reading OPTS/USE_MIN inside one_fit."""
        src = (SCRIPTS / script).read_text()
        tree = ast.parse(src)
        bad = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "one_fit":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Name) and sub.id in {"OPTS", "USE_MIN"}:
                        bad.append(sub.id)
        assert not bad, (
            f"{script}: one_fit reads {sorted(set(bad))} from module state, which "
            f"a spawned worker cannot see. Pass it through the args tuple.")


# --------------------------------------------------------------------------
# 3. the option must actually change the artefact
# --------------------------------------------------------------------------
class TestOptionsChangeTheArtefact:
    @pytest.fixture
    def setup(self):
        from flubnf.sihrs_fit import StateSetup
        return StateSetup(state="T", fips="01", population=5_000_000, gamma=2.188,
                          rho=0.02, rhomult=1e-3, gammaH=1.17, omega=0.019,
                          s0=0.85, i0=2e-4, attack_rate=0.18, n_obs=5,
                          observed=np.array([1.0, 2, 3, 4, 5]))

    def test_min_model_changes_the_free_parameter_count(self, setup):
        sys.path.insert(0, str(ROOT))
        from scripts.rt_prior_run import write_conf_rt
        counts = {}
        for mm in (False, True):
            d = Path(tempfile.mkdtemp())
            c = write_conf_rt(setup, model=d / "m", exp=d / "e", out_dir=d / "o",
                              conf_path=d / "c.conf", iters=100, plo=0.6, phi=2.0,
                              seasonal=None, min_model=mm)
            txt = c.read_text()
            counts[mm] = len(re.findall(r"^(?:log)?uniform_var = ", txt, re.M))
            if mm:
                for dropped in ("eps2__FREE", "phi2__FREE", "impr__FREE"):
                    assert dropped not in txt
        assert counts[False] == 8 and counts[True] == 5, counts

    def test_window_weeks_changes_the_fitting_window(self):
        sys.path.insert(0, str(ROOT))
        from scripts.vintage_run import effective_season_start
        full = effective_season_start("2026-01-24", "2025-08-01", None)
        w12 = effective_season_start("2026-01-24", "2025-08-01", 12)
        assert full == "2025-08-01"
        assert w12 == "2025-11-01", w12
        assert w12 != full, (
            "the window flag no longer moves the season start -- this is exactly "
            "the silent failure that made three window arms identical")
