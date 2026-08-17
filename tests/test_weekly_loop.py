"""The schedule is pure, so it can be driven with a fake fitter."""
import sys, numpy as np, pytest
sys.path.insert(0,'.')
from flubnf.weekly_loop import LoopPlan, run_week
from flubnf.warmstart import Posterior

PR={"Reff__FREE":(0.6,2.5),"mult__FREE":(0.002,1.0),"r__FREE":(0.1,40.0)}
def post(pin=None, obj=100.0, priors=None):
    """Posterior relative to the CURRENT priors -- see note in the loop tests."""
    rng=np.random.default_rng(0); med={}; samp={}
    for k,(lo,hi) in (priors or PR).items():
        if pin==k: v=lo; s=np.full(400,lo)
        else: v=(lo+hi)/2; s=np.clip(rng.normal(v,(hi-lo)*0.05,400),lo,hi)
        med[k]=v; samp[k]=s
    return Posterior(med,samp,obj,4)

def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}")
    return cond

ok=True
# 1. clean from the start -> 2 probes then commit
calls=[]
def f_clean(r): calls.append(r.kind); return True, post(priors=r.priors)
st=run_week(LoopPlan(budget_s=7*3600, n_states=52), PR, f_clean)
ok &= check("clean run: 2 probes then 1 commit", calls==["probe","probe","commit"])
ok &= check("committed", st.summary()["committed"])

# 2. persistent pin -> never commits early, caps at max_probe_rounds
calls=[]
def f_pin(r): calls.append(r.kind); return True, post(pin="mult__FREE", priors=r.priors)
st=run_week(LoopPlan(budget_s=7*3600, n_states=52, max_probe_rounds=3), PR, f_pin)
ok &= check("persistent pin: 3 probes then forced commit",
           calls==["probe","probe","probe","commit"])
ok &= check("bounds were widened", st.summary()["final_priors"]["mult__FREE"]!=PR["mult__FREE"])

# 3. a clean round straight after a bound change must NOT count toward the
#    streak -- it tested a different model than the previous clean round would
#    have. Round 0 pins and widens; rounds 1 and 2 are clean; only round 2 can
#    complete the streak, so commit must not happen before round 3.
calls=[]
def f_mix(r):
    idx=len(calls); calls.append(r.kind)
    return True, (post(pin="mult__FREE", priors=r.priors) if idx==0
                  else post(priors=r.priors))
st=run_week(LoopPlan(budget_s=7*3600, n_states=52, max_probe_rounds=9), PR, f_mix)
ok &= check("clean-after-widen does not count: 3 probes before commit",
           calls==["probe","probe","probe","commit"])
ok &= check("widen happened exactly once", sum(r.bounds_changed for r in st.rounds)==1)

# 4. tiny budget -> no round at all, nothing crashes
st=run_week(LoopPlan(budget_s=1.0, n_states=52), PR, f_clean)
ok &= check("tiny budget yields no rounds", st.summary()["rounds"]==0)

# 5. a failed round resets the streak and is never 'best'
calls=[]
def f_fail(r):
    calls.append(r.kind)
    return (False, None) if len(calls)==1 else (True, post())
st=run_week(LoopPlan(budget_s=7*3600, n_states=52), PR, f_fail)
ok &= check("failed round does not become best", st.best is not None and st.best.ok)

# 6. round-cost model matches the measured ceiling
p=LoopPlan(budget_s=0, n_states=52, fits_per_min=2.1)
ok &= check("52 states x 2000 iters ~= 50 min", 45*60 < p.round_cost_s(2000) < 55*60)
ok &= check("52 states x 5000 iters ~= 2.1 h", 1.9*3600 < p.round_cost_s(5000) < 2.3*3600)

# 6. trusted start (task #27): a clean prior week skips the probe phase
calls=[]
st=run_week(LoopPlan(budget_s=7*3600, n_states=52), PR, f_clean,
            prev=post(priors=PR), trusted=True)
ok &= check("trusted week goes straight to commit", calls==["commit"])
calls=[]
run_week(LoopPlan(budget_s=7*3600, n_states=52), PR, f_clean,
         prev=post(priors=PR), trusted=False)
ok &= check("untrusted week still probes first", calls[0]=="probe")

print("\nALL PASS" if ok else "\nFAILURES ABOVE")

def test_schedule_suite():
    """pytest entry: the module-level checks above already ran at import."""
    assert ok, "one or more schedule checks failed (see stdout)"

if __name__ == "__main__":
    sys.exit(0 if ok else 1)

