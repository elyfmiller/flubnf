# Slope-anchored transmission member: design note

**Status:** pre-registered and frozen, not run. 2026-08-23.

**Pre-registration hash:** `5a895f3c02e06af1`
(sha256 over `gate.py` then `anchor_math.py`, first 16 hex; the formulas live in
the second file, so hashing the first alone would not freeze them)

| file | sha256 |
|---|---|
| `gate.py` | `13a892b664b76a7558eaa85d040646c8a74eea489d0440d0230654799f968c55` |
| `anchor_math.py` | `539a1cc292c7d3acc90c5dbf56e5c965fd99c277bf80bc3e5363f3bea7fb5fd9` |

The adaptive-transmission arm's verdict was deliberately not read before
freezing. `research/adaptive-beta/out/result_armA.json` was never opened, so no
bar below can have been set against that result.

---

## 1. What the member is

The production SIHRS particle filter, unchanged in every fitted respect, whose
transmission level at the forecast origin is derived from data rather than
inferred, and then held forward while depletion, waning and the seasonal
harmonic evolve the trajectory.

At each forecast origin, from the last `k = 2` vintage-true observations:

```
g_raw   = ( log y(t0) - log y(t0-1) ) / dt            weekly log-growth
v_noise = ( 1/y(t0) + 1/y(t0-1) + 2/r0 ) / dt^2       NB counting noise, r0 = 20
w       = V_SIG / (V_SIG + v_noise)                   V_SIG = 0.075
g_hat   = w * g_raw
R*      = clip( 1 + g_hat / gamma , 0.70 , 1.30 )
```

and then, per particle `i`, using the filter's own latent susceptible fraction
`s_i(t0)` and the particle's own harmonic:

```
Reff_i  <-  R* * s0 / ( s_i(t0) * exp( eps1_i cos(2 pi (t0 - phi1_i)/52) ) )
```

**Fitted parameters: 5. Added dimensions: zero.** The likelihood, the priors,
the Liu-West jitter, the resampling and the rng stream through the origin are
byte-identical to production. That is not a claim, it is a mechanical
consequence of the implementation in section 4, and it is checked (assertion b'
in `gate.py` section 5).

### The algebra, against the system as implemented

`beta0 = Reff*gamma/s0` and `beta(t) = beta0 exp(eps1 cos(2 pi (t-phi1)/52))`,
so with `s = S/N`:

```
R_eff(t)      = Reff * exp(eps1 cos(2 pi (t-phi1)/52)) * s(t)/s0      (1)
d log I / dt  = beta(t) s(t) - gamma = gamma ( R_eff(t) - 1 )         (2)
R*            = 1 + g / gamma                                         (3)
```

The observable is the *integrated* weekly admission flux, whose weekly log
change equals `d log I / dt` in an exponential phase, so (2) inverts to (3)
without an extra approximation. The tasking's expression
`R = (g/gamma + 1)/S(t0)` is (3) divided by the susceptible fraction: that is
`beta/gamma`, the scale-free transmissibility, not `R_eff`. Both appear above;
(3) is what the member fixes and the transmissibility is what is held constant
forward.

### The harmonic is RETAINED in the primary

Three registered grounds. RW-beta set `eps1 = 0` and was killed, so repeating
that one decision would confound the new idea with an old one. The member's
claim is about the *level* of transmission, not its calendar shape, and
disabling the harmonic changes two things at once. And the harmonic supplies
33% of the downward pressure on `log R_eff` against depletion's 25%, so removing
it biases the member toward turning late for a reason unrelated to anchoring.
The disabled version (`S0h`) is a reported-only mechanism control that measures
exactly that bias.

### Why `k = 2`

It is the estimator this project's own R_eff audit measured against the filter,
not the simplest one. At turn weeks its directional AUC is 0.755 against the
model R_eff's 0.717, and its implied `R = 1` crossing is within one week of the
observed peak 70.1% of the time against 57.7%. `k = 4` (an OLS slope) is
registered as a reported-only robustness arm.

### Why `V_SIG = 0.075`

Measured, not chosen, by variance components on vintage truth over the exact
gate panel (510 origins, `calibrate.py`):

| estimator | var(g_raw) | median v_noise | implied V_SIG |
|---|---|---|---|
| k = 2 | 0.2779 | 0.1327 | 0.145 |
| k = 4 | 0.0879 | 0.0132 | **0.075** |

The two disagree for a reason that decides which to use: the member *holds* R*
fixed across the horizon, so the quantity worth preserving is the persistent
component of weekly growth, which the four-point slope isolates. The two-point
figure also contains one-week transients that will not survive four weeks and
should be shrunk. 0.145 is kept as one of the two sensitivity arms.

### Guards, all frozen before any fit

| guard | constant | rationale |
|---|---|---|
| clip on R* | `[0.70, 1.30]` | the 156 sealed reference fits put the filter's own R_eff in 0.805 to 1.498 with every season's IQR inside [0.87, 1.15]; the audit's skill table measures relWIS 2.6 to 3.9 once origin R_eff exceeds 1.2 |
| shrinkage target | `g = 0`, i.e. `R_eff = 1` | persistence, this project's measured point-forecast ceiling. Shrinking toward the calendar climatology would import the analogue and guarantee redundancy |
| non-positive or missing count | `w = 0` | collapses to "hold R_eff at 1" rather than extrapolating noise |
| gap between the two points | `> 2` weeks gives `w = 0` | `StateSetup.times` carries true offsets, so the NHSN pause shows as a gap rather than a compressed series |
| susceptible-fraction floor | `s_i(t0) >= 0.05` | a degenerate particle may not divide by ~0 |
| anchor-scale guard | flag outside `[1/3, 3]`, drop outside `[1/10, 10]` | earned by the 2026-08-23 COVID autopsy, where a collapsed cloud drove the collection-time scale to 95.3 and the rescaled median to zero at h = 3-4 |
| no completeness correction | none | that mechanism was killed twice here, cross-season and rolling. The implied bias of the incomplete newest point is reported instead |

Consequence, stated before the run: at panel counts `w` lands near 0.36 to
0.42, `sd(g_hat) = sqrt(V_SIG * w)` is about 0.17, and R* sits at 1.00 with a
spread near 0.08 in R_eff units. That is correct shrinkage-estimator behaviour.
The member will not blow up at takeoff, and it will not turn sharply either.

---

## 2. The gates, with their numeric bars

Panel: 6 states (Alaska, California, New York, Pennsylvania, Vermont, Wyoming)
x 3 seasons x 85 sealed as-of dates x 3 replicates = **1,530 fits**, 10k
particles, jitter 0.30, integrated observable. Identical to the
adaptive-transmission arm's panel, so the two members are directly comparable.
Panel is triage: a pass licenses a full-grid run and nothing else.

### Gate 1: redundancy, first, before any skill number

Measured on the **growth factor** `G = log(q50_h / y_origin)`, never on medians.
Every member here is anchored to the same last observation (the analogue
multiplies it by donor ratios, `pf.collect` rescales the filter's origin median
onto it), so a correlation of medians is a correlation of the anchor and
measures nothing.

| clause | statistic | KILL at |
|---|---|---|
| 1a growth | pooled Pearson r of `G` against each of analogue and production pf | `>= 0.90` against either |
| 1b error | pooled Pearson r of `log(WIS+1)` per cell against each | `>= 0.85` against either |

`r(pf, analogue)` is computed on the same cells and reported beside both, so the
bars are read against the pair the project already treats as complementary.
Gate 1a is also reported at all three `V_SIG` values, because heavier shrinkage
makes the member both safer and more analogue-like and that trade is registered
rather than discovered.

**Registered expectation.** The analogue clause is unlikely to fire, for a
structural reason: `donor_ratios()` pools donors across states and never
conditions on the target state, so the analogue's growth factor is constant
across states within an (as-of, horizon) block while a slope anchor's varies
entirely within it. The clause with teeth is the one against the **production
filter**, which shares this member's latent state and differs only in the
forward transmission level. The tasking named the analogue; both are gated and
the verdict names which fired.

### Gate 2: the turn

**2a implied-turn timing.** Each origin cloud is propagated 30 weeks by the
audit's own vectorised RK4 (`anchor_math.propagate`, mirrored byte-for-byte from
`context/reff/implied_peak.py`, including its H quasi-steady reconstruction and
its `median(t) - 1` model-clock convention) under production parameters and
under anchored parameters. `pw_err = weighted-median implied peak week minus the
centred-3-week-smoothed settled peak week`, restricted to origins strictly
before the observed peak.

| clause | bar |
|---|---|
| 2a-i late-turn kill | paired median of `(member pw_err - production pw_err)` **<= +1.0 week** |
| 2a-ii accuracy floor | member fraction `|pw_err| <= 2` **>= 0.90 x** production's on the same cells |

Comparators printed beside: the audit's full-grid production figures, median
`pw_err` -1.00 wk, IQR [-4, +1], `|err| <= 1` 37.8%, `|err| <= 2` 58.4%, 95%
interval covering the true peak week 97.0%. If the panel recomputation
disagrees, the recomputed production value is the comparator.

**2b coverage at the two turns, both directions**, on the 3-member equal-weight
ensemble. Bars copied unchanged from the adaptive-transmission arm so the
members are comparable:

| window | bar | incumbent |
|---|---|---|
| as-of month 2025-01 (peak) | cov50 **> 0.35** | 0.236, too narrow |
| as-of month 2024-02 (plateau) | cov50 **< 0.78** | 0.743, too wide |

Reported beside, not gated: the member's own cov50 and cov95 in both windows
and the over/under split (`y > q97.5` and `y < q2.5`), which says whether a
coverage miss is placement or width.

### Gate 3: skill and width

| clause | bar |
|---|---|
| 3a width pre-screen | computed and printed **before any relWIS**: mean width at 50/80/95 with empirical coverage beside each, plus width at matched coverage against production pf, on all cells and on turn cells. Not itself a kill; a matched ratio above 1 is stated in the verdict line |
| 3b ensemble | 3-member equal-weight relWIS **below** 2-member 50/50, pooled over 2023-24 + 2024-25; 2025-26 reported as held-out confirmation |
| 3c member floor | member's own relWIS **< 1.1** in every season |

### Gate 4: the COVID rider

3 states x 3 origins x 3 replicates = 27 fits, production settings,
break-excluded cells, season start 2025-06-01. The paired control is written by
the same run.

**Bimodality is declared VOID, not passed or failed**, with the reason attached
so its absence can never be read as a pass. The round-two estimator asks whether
the fitted model has a limit cycle. This member's forward transmission is a
deterministic function of the last two data points, so its skeleton is the
production skeleton with one constant re-levelled and returns 1.00 peaks per
year by construction, and there is no stochastic process for a generative
estimator to run on. Reporting 1.00 would report the estimator, not the member.

| clause | bar |
|---|---|
| C1 turn responsiveness (replaces bimodality) | sign agreement between `(R* - 1)` and the realized 4-week log change; member accuracy **>=** the control's on identical cells, paired sign-test p reported beside |
| C2 width | central-95 relative to actual **<= 4.06** with coverage beside it, reported absolutely and as a ratio to the paired control. Standing number of record: the production COVID PF's 1.689 at 100% coverage |
| C3 anchor validity | clipping **< 0.40** and median shrinkage weight **>= 0.20** |

COVID's gamma is roughly half influenza's (7/6.84 per week, Manica 2022
intrinsic generation time), so `R* = 1 + g/gamma` swings about twice as far per
unit of `g` there and the same clip box is a tighter rail. Its firing rate is
reported separately rather than pooled with influenza's. COVID carries no skill
claim.

### Reported, never gated

Per-horizon relWIS; the distributions of R* and of the filter's own origin
R_eff side by side; clip fractions, shrinkage weights, and
`SPREAD_RATIO = sd(R*) / sd(R_eff production)`; the anchor-scale guard's counts;
filter failure counts; the `S0h`, `S1a`, `S1b` and `S4` variants.

**Persistence clause.** If `SPREAD_RATIO < 0.25` the verdict line reads
"shrunken-persistence forecaster, not a slope-anchored one". That is a statement
about what was tested rather than a failure, because this project's measured
point-forecast ceiling *is* persistence, but the write-up must then not claim
that deriving transmission from slope was what was measured.

---

## 3. Files

| file | role |
|---|---|
| `anchor_math.py` | the algebra and the RK4 skeleton, numpy only, imported by both the engine venv (py3.10) and the analysis venv (py3.12) so the filter and the scorer cannot drift |
| `gate.py` | the pre-registration, the frozen constants, cell preparation, the generated runner, collection with the anchor-scale guard |
| `score.py` | the gates, mechanically, with every bar imported from `gate.py` |
| `covid_gate.py` | the COVID rider |
| `calibrate.py` | reproduces the `V_SIG` variance-components measurement from truth alone |
| `smoke.py` | `--math` (pure numpy, seconds) and `--filter` (one cell, 400 particles) |

---

## 4. Implementation: nothing in `pybnf` is touched

`ParticleFilter._write_outputs` is the exact seam. It runs once per replicate,
after the last likelihood evaluation, and already resamples the cloud to equal
weights and propagates a copy of theta forward with transmission frozen. The
member is a **subclass defined inside the generated runner**:

```python
def _write_outputs(self, cloud, mu_hist, repl, rng):
    super()._write_outputs(cloud, mu_hist, repl, rng)   # production, bit-identical
    ...                                                 # anchored forwards, own rng
```

Four consequences, all load-bearing:

- `pybnf/pf.py` is not edited, so this candidate **cannot disturb the
  adaptive-transmission experiment** running against the same worktree. The two
  contend only for cores.
- The production forward keeps the parent's rng consumption exactly, which is
  what makes assertion (b') possible: **this run's own production forecast must
  reproduce the seal's stored per-cell pf WIS to 1e-6.** Every previous member
  gate ran a different template and could only compare against stored samples.
  If (b') fails, the run stops, because it would mean the construction perturbed
  something upstream of the origin and the zero-added-dimension claim is false.
- The anchored variants share one resample draw on a separate deterministic
  stream, so variant-to-variant comparisons carry no extra Monte Carlo noise.
  The only difference from the control's draw is a single systematic resample
  out of 10,000 particles, and that is stated rather than hidden.
- The per-cell anchor inputs travel in `anchor.json`, not in the conf, so the
  conf handed to `load_config` is exactly the production conf and no unknown key
  can change parsing.

Species indices for S, I and the model clock are parsed from the generated
`m.net` and asserted against the template's seed-species order; a template whose
order changed fails loudly rather than anchoring on the wrong compartment.

The math smoke has been run and passes, including the reduction property that a
structural elaboration must satisfy: anchoring every particle at its own current
`R_eff` returns the parameter vector unchanged to 1e-10.

---

## 5. Machine cost

Measured baseline, from the adaptive-transmission arm's own shard progress files
(read 2026-08-23, under contention from a concurrent COVID arm): **175 cells in
4,328 s per shard at 4 shards**, i.e. 24.7 s per cell per shard, 583 cells/hour
aggregate.

This member's per-cell cost differs in two directions. The assimilation phase is
*cheaper* (5 parameters, no AR(1) step, no weekly diagnostic). The forward phase
is dearer: five four-week loops instead of one, which at a median of about 30
assimilated weeks per cell is roughly +13% each, +53% total. Net about 1.5x.

| arm | cells | shards | estimated wall |
|---|---|---|---|
| preparation (netgen, parallel) | 1,530 | 4 | 30 to 90 s |
| **influenza, all variants + paired control** | 1,530 | 4 | **3.5 to 5 h** |
| the same at 6 shards | 1,530 | 6 | 2.4 to 3.4 h |
| scoring, including the 30-week RK4 turn propagation | - | 1 | 5 to 15 min |
| **COVID rider + its paired control** | 27 | 3 | **15 to 40 min** |
| smoke, math then one 400-particle cell | 1 | 1 | under 2 min |

**Total: about 4 to 5.5 hours** for everything, with the paired production
control included at zero extra cost because it is written by the same run.

Storage: roughly 1 to 1.7 MB per cell in `compact.npz` (production trajectory,
five variant trajectories, params, and the origin cloud), so **2 to 3 GB** in
the scratchpad. Check free space before launching.

---

## 6. Launch, when the machine is free

Prerequisite: the adaptive-transmission arms and their COVID rider have
finished. There is no code conflict, only CPU contention, so this is a
scheduling decision rather than a correctness one.

```bash
cd ~/Documents/GitHub/flubnf
mkdir -p research/slope-anchored/out

# 1. smoke, in this order. --filter is the one that matters: it asserts the
#    subclass leaves the production forward bit-identical.
./.venv/bin/python research/slope-anchored/smoke.py --math
./.venv/bin/python research/slope-anchored/smoke.py --filter

# 2. reproduce the frozen V_SIG calibration (truth only, no fit)
./.venv/bin/python research/slope-anchored/calibrate.py \
    2>&1 | tee research/slope-anchored/out/calibrate.log

# 3. the influenza arm. gate.py launches nice'd shards and RETURNS, so the
#    shards outlive the shell. caffeinate must therefore be detached with its
#    own lifetime rather than wrapped around gate.py, which would exit in
#    seconds and take the sleep hold with it. 7 hours covers the estimate with
#    margin. Confirm macOS automatic updates are deferred before launching:
#    an update restart has killed multi-hour runs on this machine before.
nohup caffeinate -dimsu -t 25200 >/dev/null 2>&1 &

./.venv/bin/python research/slope-anchored/gate.py \
    --run --shards 4 --nice 12 \
    2>&1 | tee research/slope-anchored/out/run.log

# 4. poll
cat "${SLOPEANCHOR_WORK:-/private/tmp/claude-1786722491/-Users-l-biosci-posnerlab-Documents-GitHub-NAU-Projects-NAU-Influenza-M-Model/ab76ceee-c2c4-485d-b683-7b08e1248f4e/scratchpad/slopeanchor}"/status_*.json.prog

# 5. score, once every shard reports done == total
./.venv/bin/python research/slope-anchored/score.py \
    2>&1 | tee research/slope-anchored/out/score.log

# 6. the COVID rider
./.venv/bin/python research/slope-anchored/covid_gate.py --run --shards 3 \
    2>&1 | tee research/slope-anchored/out/covid_run.log
./.venv/bin/python research/slope-anchored/covid_gate.py --score \
    2>&1 | tee research/slope-anchored/out/covid_score.log
```

Both `gate.py --run` and `score.py` are resumable and idempotent: a prepared
cell directory is reused, and a cell with a `compact.npz` is skipped.

---

## 7. Honest assessment: which gate this most likely fails

Ranked, written before any fit.

1. **Gate 2a-i, the late-turn clause. The most likely kill.** The measured
   shrinkage puts R* at 1.00 with a spread near 0.08 in R_eff units. A
   near-critical R_eff turns only as fast as depletion (25% of the weekly log
   R_eff movement) and the retained harmonic (33%) can pull it down, which is
   slow. The comparator is a production filter that already sits below R_eff = 1
   at 52.8% of origins and whose implied peak is *early* by a median of one
   week. A member biased toward R_eff = 1 will be later than a comparator that
   is already early, and the bar allows only one week of slippage.
   The audit's two-point advantage does not rescue this: that result is
   retrospective and directional, measured week by week over whole seasons, and
   says the rule detects a turn promptly *after* it happens. Gate 2a tests
   forward timing from origins *before* the peak, which is a different object.
2. **Gate 2b, the January direction.** Imposing one R* on every particle removes
   the between-particle spread in origin transmission, so the member is a
   natural width reducer, and the incumbent already covers only 0.236 at the
   Jan-2025 peak. This is the same underlying defect as (1) seen through a
   different instrument, which is why they are likely to fire together.
3. **Gate 3b, the ensemble bar.** Independent of mechanism, this exact bar has a
   nought-for-eight record in this project, and the two-strain member showed it
   can be cleared on the panel and fail at full grid.
4. **Gate 1a against the production filter.** Same latent state, same mechanism,
   only a re-levelled forward transmission, and the re-levelling is heavily
   shrunk toward the filter's own neighbourhood. A growth-factor correlation
   above 0.90 is plausible.
5. **Gate 1a against the calendar analogue, the clause the tasking named. The
   least likely to fire**, for the structural reason in section 2: the
   analogue's growth factor carries no state variation at all. The place to look
   for the effect is the `V_SIG = 0.145` sensitivity arm, where lighter
   shrinkage restores state variation, and the `V_SIG = 0.04` arm, where heavier
   shrinkage removes it.
6. **Gate 3c, the member floor.** Least likely. The member is a small
   perturbation of a filter whose panel relWIS is 0.876 / 0.558 / 0.654.

The most valuable outcome is not a pass. It is the paired production control:
because assimilation is identical and only the forward rule differs, this run
measures, for the first time in this project, exactly what the filter's own
transmission *estimate* is worth against a direct *measurement* of the same
quantity, on identical latent states. That number is informative whichever way
the gates fall.
