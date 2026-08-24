"""Pre-launch smoke for the slope-anchored member.

Two sections, deliberately separable:

  --math   pure numpy, no fit, seconds. Checks the anchor algebra against
           itself, including the REDUCTION property that a structural
           elaboration must satisfy: anchoring every particle at its OWN
           current R_eff must return the parameter vector unchanged. A member
           that does not reduce to the model it elaborates is testing a
           different model (the age-structure screen's lesson, 2026-08).

  --filter one real cell at 400 particles. Checks the property the whole
           design rests on: the production forward written by the subclass is
           BIT-IDENTICAL to the same conf run through the unmodified
           ParticleFilter. If that fails, the zero-added-dimension claim is
           false and nothing downstream is worth running.

Run:  ./.venv/bin/python research/slope-anchored/smoke.py --math
      ./.venv/bin/python research/slope-anchored/smoke.py --filter
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))

import anchor_math as AM                                      # noqa: E402
import gate                                                   # noqa: E402

NAMES = ["Reff__FREE", "eps1__FREE", "phi1__FREE", "mult__FREE", "r__FREE"]


def check_math() -> None:
    rng = np.random.default_rng(0)
    P = 5000
    theta = np.column_stack([
        rng.uniform(0.6, 2.5, P), rng.uniform(0.0, 1.0, P),
        rng.uniform(0.0, 52.0, P), rng.uniform(0.002, 1.0, P),
        rng.uniform(0.1, 40.0, P)])
    s_frac = rng.uniform(0.2, 0.9, P)
    s0, t0 = 0.85, 23.4
    gamma = 7.0 / 3.2

    # 1. the anchor hits its target exactly, harmonic retained
    for rstar in (0.70, 0.95, 1.00, 1.30):
        th = AM.apply_anchor(theta, NAMES, rstar, s_frac, s0, t0, True)
        got = AM.model_reff(th[:, 0], th[:, 1], th[:, 2], s_frac, s0, t0)
        assert np.allclose(got, rstar, rtol=1e-12), (rstar, got[:3])
    print("  [ok] harmonic-retained anchor hits R* exactly")

    # 2. harmonic disabled: R_eff(t0) = R*, and beta is constant forward, so
    #    R_eff(t) = R* s(t)/s(t0) for any later t
    th = AM.apply_anchor(theta, NAMES, 1.10, s_frac, s0, t0, False)
    assert np.allclose(th[:, 1], 0.0)
    got = AM.model_reff(th[:, 0], th[:, 1], th[:, 2], s_frac, s0, t0)
    assert np.allclose(got, 1.10, rtol=1e-12)
    s_later = s_frac * 0.9
    got_later = AM.model_reff(th[:, 0], th[:, 1], th[:, 2], s_later, s0,
                              t0 + 4.0)
    assert np.allclose(got_later, 1.10 * 0.9, rtol=1e-12)
    print("  [ok] harmonic-disabled anchor holds beta constant forward")

    # 3. REDUCTION: anchoring each particle at its own current R_eff is a no-op
    own = AM.model_reff(theta[:, 0], theta[:, 1], theta[:, 2], s_frac, s0, t0)
    reff_back = AM.anchored_reff(1.0, s_frac, s0, theta[:, 1], theta[:, 2],
                                 t0, True) * own
    assert np.allclose(reff_back, theta[:, 0], rtol=1e-10), \
        "the anchor does not reduce to the model it elaborates"
    print("  [ok] reduction: anchoring at the particle's own R_eff is a no-op")

    # 4. only the transmission columns move
    th = AM.apply_anchor(theta, NAMES, 1.05, s_frac, s0, t0, True)
    for j, nm in enumerate(NAMES):
        if nm in ("Reff__FREE",):
            continue
        assert np.array_equal(th[:, j], theta[:, j]), nm
    print("  [ok] mult, r and phi1 are untouched")

    # 5. the growth estimator's guards
    for y, t, why in (([10.0, 0.0], [0, 1], "nonpositive_or_missing"),
                      ([10.0, 12.0], [0, 5], "gap_too_wide"),
                      ([10.0], [0], "too_few_points")):
        g = AM.growth_estimate(np.array(y), np.array(t), k=2)
        assert g["reason"] == why and g["w"] == 0.0, (y, t, g)
    print("  [ok] guards collapse to w = 0 rather than extrapolating noise")

    # 6. shrinkage is monotone in count size and never exceeds 1
    ws = [AM.growth_estimate(np.array([y0, y0 * 1.5]), np.array([0, 1]),
                             k=2)["w"] for y0 in (5, 50, 500, 5000)]
    assert all(a < b for a, b in zip(ws, ws[1:])) and max(ws) < 1.0, ws
    print(f"  [ok] shrinkage weight rises with counts: "
          f"{[round(w, 3) for w in ws]}")

    # 7. the clip box, and R* = 1 exactly at g = 0
    assert AM.r_star(0.0, gamma)["r_star"] == 1.0
    assert AM.r_star(+9.0, gamma)["clipped_high"]
    assert AM.r_star(-9.0, gamma)["clipped_low"]
    print("  [ok] clip box and the g = 0 identity")
    print(f"\nMATH SMOKE PASSED. pre-registration "
          f"{gate.preregistration_hash()}")


def check_filter(particles: int = 400) -> None:
    """One real cell, twice: unmodified filter, then the subclass."""
    from flubnf.settings import PY_ENGINE, PYBNF
    season, asof, loc = "2024-25", "2025-01-11", "Vermont"
    root = gate.WORK / "_smoke"
    shutil.rmtree(root, ignore_errors=True)
    d = root / "cell"
    meta = gate.prepare_cell(d, loc, asof, season, 0)
    conf = (d / "pf.conf").read_text().replace(
        f"num_particles = {gate.PARTICLES}", f"num_particles = {particles}")
    (d / "pf.conf").write_text(conf)
    script = f'''
import json, os, shutil, sys
sys.path.insert(0, {str(PYBNF)!r}); sys.path.insert(0, {str(HERE)!r})
from pathlib import Path
import numpy as np
d = Path({str(d)!r})
os.chdir(d)
from pybnf.parse import load_config
from pybnf.pf import ParticleFilter
out = {{}}
for mode in ("plain", "subclass"):
    shutil.rmtree(d / "out", ignore_errors=True)
    (d / "out" / "Results").mkdir(parents=True)
    if mode == "plain":
        ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
    else:
        sys.argv = ["x"]
        exec(open({str(HERE / "_subclass_snippet.py")!r}).read(), globals())
        alg = SlopeAnchoredPF(load_config(str(d / "pf.conf")))
        alg.anchor = json.load(open(d / "anchor.json"))
        alg.run(None)
    runs = d / "out" / "Results" / "A_MCMC" / "Runs"
    f = sorted(runs.glob("*traj_noise*"))[0]
    out[mode] = np.genfromtxt(f)
    if mode == "subclass":
        out["variants"] = {{p.name: float(np.median(np.genfromtxt(p)[:, -1]))
                            for p in sorted(runs.glob("traj_slope_*"))}}
same = bool(np.array_equal(out["plain"], out["subclass"]))
json.dump({{"bit_identical": same,
            "variant_medians": out["variants"]}},
          open(str(d / "smoke.json"), "w"))
print("bit identical:", same)
print("variant h=4 medians:", out["variants"])
'''
    _write_subclass_snippet()
    sp = root / "smoke_runner.py"
    sp.write_text(script)
    r = subprocess.run([str(PY_ENGINE), str(sp)], capture_output=True,
                       text=True, timeout=3600)
    print(r.stdout[-2000:])
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise SystemExit("filter smoke failed")
    res = json.loads((d / "smoke.json").read_text())
    assert res["bit_identical"], (
        "the subclass changed the production forward -- the "
        "zero-added-dimension claim is false; stop")
    print(f"\nFILTER SMOKE PASSED ({meta['location']} {meta['asof']}, "
          f"{particles} particles). pre-registration "
          f"{gate.preregistration_hash()}")


def _write_subclass_snippet() -> None:
    """The subclass, extracted verbatim from gate._RUNNER so the smoke tests
    the code that will actually run rather than a copy of it."""
    src = gate._RUNNER
    start = src.index("def make_class():")
    end = src.index("    return SlopeAnchoredPF")
    body = src[start:end].replace("def make_class():\n", "", 1)
    body = "\n".join(line[4:] if line.startswith("    ") else line
                     for line in body.splitlines())
    body = body.replace("{{", "{").replace("}}", "}")
    (HERE / "_subclass_snippet.py").write_text(
        "import json\nfrom pathlib import Path\nimport numpy as np\n"
        "import anchor_math as AM\n" + body + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--math", action="store_true")
    ap.add_argument("--filter", action="store_true")
    ap.add_argument("--particles", type=int, default=400)
    a = ap.parse_args()
    if a.math or not (a.math or a.filter):
        print("== math smoke ==")
        check_math()
    if a.filter:
        print("\n== filter smoke ==")
        check_filter(a.particles)


if __name__ == "__main__":
    main()
