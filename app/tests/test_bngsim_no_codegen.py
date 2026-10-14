"""bngsim with code generation off, as every Windows engine runner has it
(pf.runner_popen_kwargs sets BNGSIM_NO_CODEGEN=1, and the engine then
builds its Simulator without a compiled right-hand side): the calls a
particle filter makes, on a network the Sandbox generates, with no C
compiler on PATH.

Skipped unless FLUBNF_BNGSIM_REAL=1 (the windows-own-perl CI job): it needs
bngsim and a perl that runs BNG2.pl, and a missing one then fails rather
than skips. The engine itself is private and cannot run in CI; what it
does with the flag is read from its source (BngsimModel skips
prepare_codegen when BNGSIM_NO_CODEGEN is set).
"""
import logging
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest                                            # noqa: E402

from app.core import sandbox as sb                       # noqa: E402
from flubnf import settings                              # noqa: E402

pytestmark = pytest.mark.skipif(os.environ.get("FLUBNF_BNGSIM_REAL") != "1",
                                reason="FLUBNF_BNGSIM_REAL=1 runs bngsim for real")

#: a Sandbox quick check's shape, small: particles, weekly segments, and
#: the engine's points per segment (STEPS_PER_INTERVAL + 1)
PARTICLES, WEEKS, POINTS = 50, 12, 8


@pytest.fixture(scope="module")
def net(tmp_path_factory):
    """m.net for the SIR example, generated as a Sandbox run does it."""
    import bionetgen
    bng = (Path(bionetgen.__file__).parent / settings.bng_platform_dirs()[0]
           / "BNG2.pl")
    assert bng.is_file(), bng
    assert settings.resolve_perl(), "no perl that runs BNG2.pl"
    cell = tmp_path_factory.mktemp("cell")
    shutil.copy(sb.EXAMPLES / "sir_example" / "model.bngl", cell / "m.bngl")
    old, sb.BNG = sb.BNG, str(bng)
    try:
        sb._netgen(cell)
    finally:
        sb.BNG = old
    return cell / "m.net"


@pytest.fixture
def no_compiler(monkeypatch):
    """PATH without a folder that holds a C compiler (a runner has
    Strawberry's gcc, MinGW, MSYS2), as on a student's PC; CC unset."""
    keep = [d for d in os.environ.get("PATH", "").split(os.pathsep)
            if d and not any(os.path.isfile(os.path.join(d, c))
                             for c in ("gcc.exe", "cl.exe", "gcc", "cc"))]
    monkeypatch.setenv("PATH", os.pathsep.join(keep))
    monkeypatch.delenv("CC", raising=False)
    assert shutil.which("gcc") is None and shutil.which("cl") is None


def _fit_like(net):
    """The particle filter's calls (pf_simulator, then per particle per
    week): one Simulator for every particle, set_param, set_state, run,
    get_state, and the observables and expressions read back."""
    import bngsim
    import numpy as np
    model = bngsim.Model.from_net(str(net))
    sim = bngsim.Simulator(model, method="ode")
    free = [n for n in model.param_names if n.endswith("__FREE")]
    assert free, model.param_names
    base = {n: model.get_param(n) for n in free}
    rng = np.random.default_rng(12345)
    theta = {n: base[n] * np.exp(rng.normal(0, 0.15, PARTICLES)) for n in free}
    model.reset()
    states = np.tile(np.asarray(model.get_state(), float), (PARTICLES, 1))
    last = np.zeros((WEEKS, PARTICLES))
    for w in range(WEEKS):
        for p in range(PARTICLES):
            for n in free:
                model.set_param(n, float(theta[n][p]))
            sim.set_state(states[p])
            res = sim.run(t_span=(float(w), float(w + 1)), n_points=POINTS)
            states[p] = np.array(sim.get_state(), copy=True)
            np.asarray(res._core.expression_data)
            obs = np.asarray(res.observables)
            last[w, p] = obs[-1, -1]
    return sim, states, last


def test_a_fit_runs_on_the_interpreted_right_hand_side(net, no_compiler,
                                                       caplog):
    """What a Windows fit does with code generation off: every call
    succeeds, every state stays finite, and nothing tells the student to
    install Visual Studio."""
    import numpy as np
    caplog.set_level(logging.WARNING)
    sim, states, last = _fit_like(net)
    backend = getattr(sim, "codegen_backend", "exprtk")
    assert backend == "exprtk", backend
    assert np.isfinite(states).all() and np.isfinite(last).all()
    assert (last > 0).any(), "the model never produced a count"
    assert "Visual Studio" not in caplog.text


def test_without_the_flag_and_without_a_compiler_codegen_only_fails(
        net, no_compiler):
    """What the flag spares a student: with no compiler, preparing code
    generation raises (the engine turned that into a warning naming Visual
    Studio Build Tools); the interpreted run it falls back to is the same
    run, to the bit."""
    import numpy as np
    from bngsim._codegen import prepare_codegen
    with pytest.raises(Exception) as e:
        prepare_codegen(str(net))
    assert "compiler" in str(e.value).lower(), e.value
    _, a, la = _fit_like(net)
    _, b, lb = _fit_like(net)
    assert np.array_equal(a, b) and np.array_equal(la, lb)
