"""Single-state pilot for the two-age-class SIHRS candidate.

Answers ONE question, the one the draft could not settle without fitting:
**is `theta` identified, or does it just sit on its prior?**

The test is a paired pair of arms on identical data:
  * ON  -- the paediatric binomial channel carries real NHSN age counts
  * OFF -- the same model, same seed, same everything, with the channel's exp
           columns set to -1/-1 so every week is skipped
If theta's posterior is the same in both arms, the channel is not identifying
it and the mechanism is decoration. If ON concentrates and OFF does not, the
channel is doing the work it was designed to do.

NOT VINTAGE-TRUE and not meant to be. NHSN age strata have no public as-of
archive, so this pilot uses final data. It is an identifiability check, not a
skill claim, and nothing here may be quoted as a skill result.

Touches nothing under flubnf/ or app/: the filter is driven directly, the way
app/core/engines/pf.py's generated runner does.

Usage (two venvs, as the engine requires):
    ./.venv/bin/python research/candidate-age2/pilot.py prepare
    ~/.venvs/flubnf/bin/python research/candidate-age2/pilot.py run
    ./.venv/bin/python research/candidate-age2/pilot.py report
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
WORK = HERE / "pilot_work"

STATE_NAME = "California"
STATE_ABBR = "CA"
SEASON_START = "2024-08-01"
AS_OF = "2025-05-31"          # full 2024-25 season observed
VINTAGE = "2025-05-31"
PARTICLES = 4000
JITTER = 0.30
QKID = 2.0                    # children's relative contact intensity, FIXED
UKID = 1.0
NEFF_CAP = 30                 # measured: keeps the share channel ~2x the NB
                              # channel instead of ~20x at the 2-strain's 300

DEFAULTS = ("begin parameters\nReff__FREE 1.20\neps1__FREE 0.15\n"
            "phi1__FREE 22.0\ntheta__FREE 0.45\nmult__FREE 0.05\nr__FREE 8.0\n")
VARS = """uniform_var = Reff__FREE 0.6 2.5
uniform_var = eps1__FREE 0.0 1.0
uniform_var = phi1__FREE 0.0 52.0
uniform_var = theta__FREE 0.0 0.7
loguniform_var = mult__FREE 0.002 1.0
loguniform_var = r__FREE 0.1 40.0
"""
THETA_PRIOR = (0.0, 0.7)


# --------------------------------------------------------------------- data
def fetch_age(state: str) -> dict:
    """weekending -> (ped, adult, ped0to4, rate0to4, ped5to17, rate5to17)."""
    cols = ("weekendingdate,totalconfflunewadmped,totalconfflunewadmadult,"
            "numconfflunewadmped0to4,numconfflunewadmped0to4per100k,"
            "numconfflunewadmped5to17,numconfflunewadmped5to17per100k")
    url = ("https://data.cdc.gov/resource/ua7e-t2fy.json?"
           f"$select={cols}&$where=jurisdiction='{state}' AND "
           "weekendingdate between '2024-08-01' and '2025-06-30'"
           "&$order=weekendingdate&$limit=5000")
    with urllib.request.urlopen(
            url.replace(" ", "%20").replace("'", "%27"), timeout=120) as r:
        rows = json.load(r)
    out = {}
    for x in rows:
        def f(k):
            v = x.get(k)
            return None if v in (None, "") else float(v)
        out[x["weekendingdate"][:10]] = (f("totalconfflunewadmped"),
                                         f("totalconfflunewadmadult"),
                                         f("numconfflunewadmped0to4"),
                                         f("numconfflunewadmped0to4per100k"),
                                         f("numconfflunewadmped5to17"),
                                         f("numconfflunewadmped5to17per100k"))
    return out


def child_fraction(age: dict, population: float) -> float:
    """Child population share, backed out of NHSN's own per-100k rates.

    count / rate * 1e5 = the denominator CDC used for that age band, so the
    child fraction comes from the same dataset as the counts and needs no
    external census join.
    """
    pops = {"0to4": [], "5to17": []}
    for _, (_, _, n04, r04, n517, r517) in age.items():
        for band, n, r in (("0to4", n04, r04), ("5to17", n517, r517)):
            if n and r and r > 0:
                pops[band].append(n / r * 1e5)
    if not pops["0to4"] or not pops["5to17"]:
        raise SystemExit("could not derive child population from per-100k rates")
    kid_pop = float(np.median(pops["0to4"]) + np.median(pops["5to17"]))
    return kid_pop / float(population)


# ------------------------------------------------------------------ prepare
def prepare() -> int:
    import pandas as pd
    from flubnf.settings import BNG, LOCATIONS
    from flubnf.sihrs_fit import materialize_model, resolve_state
    from app.core.data import vintage_path
    sys.path.insert(0, str(HERE))
    from age2_tokens import THETA_ANCHOR, age2_tokens, check_uk, ngm

    WORK.mkdir(parents=True, exist_ok=True)
    s = resolve_state(STATE_NAME, truth_csv=vintage_path(VINTAGE),
                      locations_csv=LOCATIONS, season_start=SEASON_START,
                      as_of=AS_OF)
    check_uk(UKID, s.s0)
    age = fetch_age(STATE_ABBR)
    fk = child_fraction(age, s.population)

    shares = [p / (p + a) for (p, a, *_) in age.values()
              if p is not None and a is not None and (p + a) > 0]
    ped_share = float(np.median(shares))
    tok = age2_tokens(fk=fk, qk=QKID, rho=s.rho,
                      ped_admission_share=ped_share, uk=UKID)
    lam, pI = ngm(THETA_ANCHOR, fk, QKID, UKID)

    print(f"state           {STATE_NAME}  pop {s.population:,.0f}")
    print(f"weeks observed  {s.n_obs}  (t={int(s.times[0])}..{int(s.times[-1])})")
    print(f"child fraction  {fk:.4f}   (from NHSN per-100k denominators)")
    print(f"ped adm share   {ped_share:.4f} (season median)")
    print(f"lam(anchor)     {lam:.4f}   ped infection seed {pI:.4f}")
    print(f"rho {s.rho:.6g} -> rhoK {tok['{{RHOKID}}']}  rhoA {tok['{{RHOADULT}}']}")

    # paediatric counts by week offset from season start
    ped_by_t = {}
    for wk, (p, a, *_) in age.items():
        if p is None or a is None or (p + a) <= 0:
            continue
        t = int((pd.Timestamp(wk) - pd.Timestamp(SEASON_START)).days // 7)
        ped_by_t[t] = (int(round(p)), int(round(p + a)))

    for arm in ("on", "off"):
        d = WORK / arm
        d.mkdir(parents=True, exist_ok=True)
        sfx = f"{STATE_NAME}_flu"
        m = materialize_model(s, HERE / "SIHRS_pop_age2_min.bngl",
                              d / "m.bngl", sfx, extra_tokens=tok)
        m.write_text(m.read_text().replace("begin parameters\n", DEFAULTS, 1))
        lines = ["# time H_weekly Ped_share_bin Ped_share_n"]
        hit = 0
        for t_off, v in zip(s.times, s.observed):
            if arm == "on":
                k, n = ped_by_t.get(int(t_off), (-1, -1))
            else:
                k, n = -1, -1          # channel silenced, everything else equal
            hit += (k >= 0)
            lines.append(f"{int(t_off)} {v:.6f} {k} {n}")
        (d / f"{sfx}.exp").write_text("\n".join(lines) + "\n")
        r = subprocess.run(["perl", str(BNG), "m.bngl"], capture_output=True,
                           text=True, cwd=str(d), timeout=300)
        if not (d / "m.net").is_file():
            raise SystemExit(f"netgen failed ({arm}): {r.stdout[-400:]}")
        (d / "pf.conf").write_text(
            f"bng_command = {BNG}\n"
            f"model = {d}/m.bngl : {d}/{sfx}.exp\n"
            f"output_dir = {d}/out\n"
            "fit_type = pf\nobjfunc = neg_bin_dynamic\n"
            f"num_particles = {PARTICLES}\npf_jitter = {JITTER}\n"
            "pf_observable_mode = integrated\npf_forecast_weeks = 4\n"
            "population_size = 1\nmax_iterations = 1\nseed = 20260821\n"
            f"{VARS}pf_binom_neff_cap = {NEFF_CAP}\n")
        print(f"  arm {arm}: netgen ok, {hit} weeks with paediatric data")
    print(f"\nprepared under {WORK}")
    return 0


# ---------------------------------------------------------------------- run
def run() -> int:
    import os
    import shutil
    # The engine venv has a released `pybnf` installed; fit_type=pf lives only
    # in the FORK. Put the fork first so it shadows the installed package --
    # the same thing app/core/engines/pf.py's generated runner does.
    from flubnf.settings import PYBNF
    sys.path.insert(0, str(PYBNF))
    from pybnf.parse import load_config
    from pybnf.pf import ParticleFilter
    for arm in ("on", "off"):
        d = WORK / arm
        shutil.rmtree(d / "out", ignore_errors=True)
        (d / "out" / "Results").mkdir(parents=True)
        cwd = os.getcwd()
        os.chdir(d)
        try:
            print(f"running arm {arm}...", flush=True)
            ParticleFilter(load_config(str(d / "pf.conf"))).run(None)
            print(f"  arm {arm}: ok", flush=True)
        except Exception as e:
            print(f"  arm {arm}: FAIL {type(e).__name__}: {e}", flush=True)
        finally:
            os.chdir(cwd)
    return 0


# ------------------------------------------------------------------- report
def posterior(arm: str):
    p = WORK / arm / "out" / "Results" / "A_MCMC" / "Runs" / "params_0.txt"
    if not p.is_file():
        return None, None
    names = p.read_text().splitlines()[0].split("\t")
    return names, np.loadtxt(p, skiprows=1)


def report() -> int:
    lo, hi = THETA_PRIOR
    prior_sd = (hi - lo) / np.sqrt(12)
    print("=" * 72)
    print("AGE-2 PILOT -- is theta identified by the paediatric channel?")
    print("=" * 72)
    print(f"{STATE_NAME}, 2024-25, {PARTICLES} particles, neff cap {NEFF_CAP}")
    print(f"theta prior U({lo},{hi}): mean {(lo+hi)/2:.3f}, sd {prior_sd:.3f}\n")
    got = {}
    for arm in ("on", "off"):
        names, th = posterior(arm)
        if th is None:
            print(f"  arm {arm}: NO OUTPUT (did the run fail?)")
            continue
        got[arm] = (names, th)
    if not got:
        raise SystemExit("no posteriors to report")
    hdr = f"{'param':14}" + "".join(f"{'arm ' + a:>22}" for a in got)
    print(hdr)
    print("-" * len(hdr))
    names = got[next(iter(got))][0]
    for i, nm in enumerate(names):
        row = f"{nm:14}"
        for a, (_, th) in got.items():
            row += f"{th[:, i].mean():12.4f} +/-{th[:, i].std():7.4f}"
        print(row)
    if "on" in got and "off" in got:
        i = names.index("theta__FREE")
        on, off = got["on"][1][:, i], got["off"][1][:, i]
        print("\n--- the test ---")
        for lab, v in (("channel ON", on), ("channel OFF", off)):
            print(f"  {lab:12} mean {v.mean():.4f}  sd {v.std():.4f}  "
                  f"sd/prior_sd {v.std()/prior_sd:.3f}")
        print(f"\n  shift in mean: {on.mean()-off.mean():+.4f}")
        print(f"  sd ratio ON/OFF: {on.std()/max(off.std(),1e-12):.3f}")
        verdict = ("IDENTIFIED: the channel concentrates theta"
                   if on.std() < 0.8 * off.std()
                   else "NOT identified: theta tracks the prior with or "
                        "without the channel")
        print(f"\n  VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    sys.exit({"prepare": prepare, "run": run, "report": report}[cmd]())
