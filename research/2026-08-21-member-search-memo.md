# FluBNF member-search memo: next ensemble member / likelihood channel

**Date:** 2026-08-21
**Scope:** research memo only. No code written or modified. Every data claim below was checked live against the named API on 2026-08-21; the exact queries are in the appendix.

---

## 0. Bottom line

I ran a cheap pre-fit triage on every channel proposed in the brief, using the project's own Law 3 in its operational form: *does the candidate signal predict next week's admissions growth after conditioning on what the filter already knows?* This is the test that retired the ED signal. It takes minutes and it changed the ranking substantially, including killing a candidate I invented mid-analysis.

| candidate channel | median partial corr. with next-week growth, given own history | verdict |
|---|---|---|
| pediatric admissions growth (NHSN age strata) | **+0.32** (2024-25), 71% of jurisdictions > +0.2 | survives; strongest surviving mechanism |
| wastewater growth, *idealised* timing | **+0.19 / +0.38** (2023-24 / 2024-25) | signal is real |
| wastewater growth, *actual publication cadence* | **−0.05 / +0.11** (2023-24 / 2024-25) | dies on timeliness, not on signal |
| hospital occupancy ÷ admissions ratio | **−0.03** (raw corr. −0.43) | textbook concurrent echo; killed |

> **SUPERSEDED, 2026-08-21 (same day). The top TWO candidates below were
> tested and both failed.**
>
> **Candidate 1 (two-strain gate)** — the diagnosis it rests on is wrong. The
> member is relatively *worst* where its typed data is thickest and only beats
> the production PF where it ran on substituted HHS regional data, so the
> pre-registered gate would keep the harmful cells and discard the helpful
> ones. See `research/twostrain-decomposition/FINDINGS.md`.
>
> **Candidate 2 (age-structured)** — built, fitted, and rejected *as a
> mechanism*, but the signal survives. `theta` is sharply identified (posterior
> sd 27% of prior; with the channel silenced it sits on the prior mean). The
> member fails because it consumes the paediatric **share**, whose one large
> feature is calendar-locked and driven by the adult denominator, and which
> carries only +0.010 incremental R² on the target — while paediatric
> **growth** carries +0.030 and a partial correlation of +0.31 after
> controlling for the autoregressive term. The memo's motivating statistic is
> confirmed; the mechanism built on it consumes the wrong observable, and puts
> the share's turning point seven weeks late. Separately, NHSN age strata begin
> in 2024-25, so the 2023-24 plateau cannot be evaluated at all. See
> `research/candidate-age2/PILOT-FINDINGS.md`.
>
> **The pattern across both failures**: §3's triage screens for association
> with the target, not for information *beyond* the target's own lag. Both
> candidates passed the triage and died later on that distinction. Future
> candidates should have to clear an incremental-R²-over-AR(1) bar before
> anything is built. And the age result suggests the productive use of a
> lagged covariate is as a covariate, not as a compartmental parameter.

Ranking, by expected pooled full-grid gain net of risk:

1. **Two-strain, restricted by a vintage-true data-sufficiency rule.** The member already exists and already passes the turn gate twice. Its full-grid failure was diagnosed as thin typed-lab data. Gate it per state-week on typed-specimen volume and the failure mode is structurally removed — and the measured eligible set (§4.1) is 37 of 52 jurisdictions at the pre-registered threshold, including nearly every large state, so the prize is bigger than the handoff's "~46 thin jurisdictions" implied. Near-zero downside, weeks of work, fully vintage-honest (I verified `fluview_clinical` serves lag-1 vintages).
2. **Age-structured (2-class) SIHRS with a pediatric-share binomial channel.** Highest ceiling. The leading indicator is internal to the target stream, the share form cancels ascertainment exactly, and the age columns ship in the *preliminary* Wednesday NHSN release, so the channel is exactly as fresh as the target. Blocked by two things I could not solve: age strata begin 2024-10-12 (no 2023-24 season), and no public vintage archive exists for them.
3. **Backfill-aware likelihood (inference change, replaces the PF).** The only candidate on this list with zero vintage risk — Delphi serves genuine issue-level NHSN vintages back to 2020. The freshest observation is a median 4-5% under-report with a 10th percentile near 0.83, and the model currently treats it as complete. That bias is largest exactly where the open gap is.
4. **Wastewater, future-only.** Recommend archiving now and a stated revival trigger, not a build.
5. **Fixed-coefficient importation coupling.** Cheap, but predicted collinear with the seasonal envelope.
6. **Occupancy-ratio channel.** Tested, dead. Documented so nobody rebuilds it.
7. **Statistical member.** Argued down, with the condition under which I'd change my mind.

I am recommending against your stated first priority (wastewater) and in favour of your second (age structure), on the basis of a measurement rather than an opinion. Section 4.4 gives the arithmetic.

---

## 1. Data and vintage audit

This is the load-bearing section, since Section 6 of the brief makes vintage capability a gating property.

| source | endpoint | flu content | earliest | jurisdictions | **vintage capable?** |
|---|---|---|---|---|---|
| NHSN admissions, aggregate | Delphi `covidcast` source `nhsn` | `confirmed_admissions_flu_ew` (+ `_prelim`) | ref. week 202032 | 50 states + DC + PR + HHS + nation | **Yes, genuinely.** `as_of` works but must be an *epiweek*, not a date |
| NHSN admissions, aggregate | FluSight hub `auxiliary-data/target-data-archive/` | `target-hospital-admissions_YYYY-MM-DD.csv` | weekly files | full grid | **Yes**, weekly Saturday vintages |
| NHSN **age strata** | Socrata `ua7e-t2fy` (final) and `mpgq-jmmr` (preliminary) | `numconfflunewadmped0to4`, `ped5to17`, `adult18to49`, `adult50to64`, `adult65to74`, `adult75plus`, `unk` | **week ending 2024-10-12** | 67 | **No.** Socrata is unversioned; Delphi carries no age signals; Internet Archive holds exactly **one** snapshot of the CSV (2025-02-14) |
| NHSN prevalence / ICU | same two datasets | `totalconffluhosppats`, `totalconffluicupats`, plus reporting-hospital counts | 2020-21 season | 67 | **No**, same as above |
| NREVSS clinical labs | Delphi `fluview_clinical` | `total_a`, `total_b`, `percent_a` | long history | state | **Yes**, verified lag-1 issue |
| FluSurv-NET | Delphi `flusurv` | `rate_age_*`, `rate_flu_a`, `rate_flu_b` | long history | ~13 catchments | **No, in practice.** Every CA week of 2024-25 carries a single issue at lag 36-52 weeks |
| NWSS wastewater, influenza A | Socrata `ymmh-divb` | 319,176 sample rows, `pcr_target_mic_lin` etc. | 2021-09-15 | see below | **No.** All 319,176 rows share one `date_updated` (the dataset refresh timestamp), so no per-record publication date exists |
| WastewaterSCAN | dashboard | influenza A and B, H1/H3/H5 | — | ~190 sites | **No**, and research use requires written permission from Stanford/Emory |

Three findings deserve emphasis.

**NHSN age strata are as fresh as the target.** I confirmed the *preliminary* dataset (`mpgq-jmmr`, Wednesday release, 4-day lag) carries the flu age columns, not just the final Friday dataset. So an age channel imposes no timeliness penalty at all — unlike every external source considered here. This is the single best operational property of any candidate in this memo.

**FluSurv-NET is not a real-time source.** It is the obvious place to look for age- and strain-specific hospitalization rates, and its content is excellent. But Delphi's issue history shows California's entire 2024-25 season published at a single issue, week 202538, at lags of 36 to 52 weeks. It is a retrospective climatology source only — which is still useful, since fixed priors need no vintages.

**NWSS coverage is real but unequal, and grew across exactly the seasons you would gate on.** Sites reporting influenza A samples between 1 October and 31 March: 49 sites in 6 states (2021-22), 439/32 (2022-23), 780/48 (2023-24), 1,140/51 (2024-25), 1,184/52 (2025-26). In 2025-26 that ranges from California (89 sites) down to DC (1), New Mexico (2), Tennessee (2), Louisiana (2). North Dakota and Puerto Rico never appear. Any retrospective gate therefore compares members across a surveillance network that roughly doubled mid-window.

---

## 2. The triage test, and what it did to the ranking

### Method

For each jurisdiction and each candidate signal `x`, with `g_t = log(admissions_t / admissions_{t-1})`:

1. Regress `g_{t+1}` on `g_t` and `g_{t-1}`; keep residuals. This is a deliberately weak stand-in for "what the particle filter already knows."
2. Regress `x_t` on the same two lags; keep residuals.
3. Correlate the residuals. A signal that is a concurrent echo of the admissions stream scores ~0 here regardless of how impressive its raw correlation looks.

Caveats, stated up front because they bound how much weight this deserves. These runs use **final revised data, not vintages**, which flatters every candidate equally. The two-lag control **understates** what the filter knows, so true partial correlations are smaller than these. And these are correlations, not WIS — Law 2 applies in spirit: this is triage, and only the full-grid gate decides anything.

### Results

**Pediatric growth leads adult growth.** Testing pediatric admissions growth at week *t* against *adult* admissions growth at week *t+1*, controlling for two lags of adult growth: median partial correlation **+0.315** across 31 jurisdictions in 2024-25, with 71% above +0.2 and consistent sign (only three jurisdictions materially negative, two of them very small). The raw correlation is +0.5 to +0.8 in most states, so about half the raw association survives the benchmark. That is a genuine leading indicator.

Note that the *pediatric share level* is null on the same test (median partial +0.09, sign-incoherent across states). The information is in the pediatric **growth rate**, not the share level. This matters for how the channel is specified, and it is the sort of thing that would have looked like a failed member if specified the obvious way.

**Wastewater's problem is the calendar, not the signal.** Using a state-week wastewater growth index — the median across sites of the log week-over-week change in PMMoV-normalized concentration, requiring at least 3 sites paired across both weeks — the same test gives:

- wastewater for the *same week* as the freshest admissions: median partial **+0.19** (2023-24), **+0.38** (2024-25);
- wastewater one week staler, which is what you actually have at the Wednesday deadline: median partial **−0.05** (2023-24), **+0.11** (2024-25).

The entire usable signal is consumed by one week of publication lag. Section 4.4 works through why that week is unavoidable.

Only 26 jurisdictions had enough site continuity to compute this at all, which is a second, independent problem.

**The occupancy ratio is an echo.** Mid-analysis I noticed that NHSN publishes weekly prevalent flu hospitalizations alongside the admissions target, from the same hospitals, with reporting-hospital counts for both, back to 2020-21, for all 67 jurisdictions. The ratio prevalence/admissions cancels ascertainment exactly and approximates mean length of stay scaled by a decreasing function of the current growth rate — so it looked like an ascertainment-free, zero-lag, full-coverage growth-rate reading. Across 53 jurisdictions the correlation between `log(prevalence/admissions)` and contemporaneous log growth is **−0.75**, with 91% of jurisdictions below −0.5, robust to excluding holiday weeks.

It fails the triage test outright: median partial correlation with *next* week's growth, given the admissions history, is **−0.03**, with only 18% of jurisdictions below −0.2. It restates the growth rate the filter already computes. This is precisely the ED signal's failure mode, in a form that looks much more mechanistic. I am reporting it in full because the raw −0.75 is seductive enough that someone will rediscover it.

(There is a residue: the jurisdictions where it does carry information — WV −0.46, ID −0.30, MS −0.29, SC −0.28, AR −0.24 — are the low-count states where the admissions series is noisiest, so it acts as a variance-reduction device rather than a predictor. Since relWIS sums WIS across cells, small states carry little pooled mass, so this residue is not worth a member.)

### A pre-registration hazard I created

My age and wastewater triage runs included 2025-26 data before I split them by season. The 2025-26 numbers have therefore been *looked at* (age: +0.166; wastewater deadline-honest: +0.026). Under a strict reading of your protocol, 2025-26 is no longer a clean holdout for these two candidates.

I think the honest options are: (a) treat 2026-27 as the true holdout for the age candidate and use 2023-24 + 2024-25 + 2025-26 as the selection surface; or (b) accept a documented single-look penalty, noting that what I looked at was a correlation on final data, not a WIS on vintage-true fits, and that the look did not inform any tuning choice. I lean to (b) with the look recorded in the pre-registration, but this is your call and it should be written down before anything is fitted.

---

## 3. Proposed additions to the laws

The three results above generalise into rules that would have saved the ED program and the two-strain full-grid run.

**Law 5 — net lead, not biological lead.** A channel's usable lead is its biological lead *minus* the difference between its publication lag and the target's. Wastewater leads admissions biologically by 0-2 weeks and is published one week later than the target, so its net lead at the submission deadline is approximately zero. Compute this number before designing anything.

**Law 6 — share channels need a per-cell sufficiency gate.** The two-strain full-grid failure was not a modelling failure; it was a member paying an identifiability cost in cells where the funding channel had no information. Any ratio or share channel should ship with a pre-registered, vintage-computable, per-state-week data-sufficiency rule. The rule must be a function of data volume only, never of scores, or it becomes a fitted weight and Law 1 applies.

**Law 7 — run the echo test before fitting anything.** The partial-correlation triage in Section 2 costs minutes, requires no fitting, and is the operational form of Law 3. It would have retired the ED signal without a program, and it retired the occupancy channel here in about ten minutes.

---

## 4. Candidates, ranked

### 4.1 Two-strain restricted by a data-sufficiency rule — *rank 1*

**What changes.** Nothing in the model. The existing two-strain member joins the ensemble only in state-weeks where the NREVSS channel that funds it actually carries information; elsewhere the ensemble is exactly today's 2-member 50/50.

**Mechanism.** Already validated. Turn gate passed twice (0.953 vs PF 0.993 on the 1,248 hardest cells; 0.968 vs 1.023 in the plateau season). The diagnosed failure is that where the binomial A/(A+B) channel has too few typed specimens, it cannot identify the per-strain phase and Reff, so the member carries seven parameters funded by two.

**Measured, 2026-08-21 — the thin-data set is much smaller than the handoff assumed.** `fluview_clinical`, three seasons, in-season weeks only (epiweeks 48–09), median weekly `total_a + total_b` per jurisdiction:

| gate | *n\** | jurisdictions eligible |
| --- | --- | --- |
| SE(A-share) ≤ 0.05 | 64 | **37** |
| SE(A-share) ≤ 0.04 | 100 | 30 |
| SE(A-share) ≤ 0.03 | 178 | 21 |

Seven jurisdictions return no typed data at all (AK, DC, DE, NH, **NY**, RI, UT) and PR returns weeks with no typed positives. The rest fail only on volume: FL is the notable near-miss at 43/week.

This does not square with "thin in ~46 jurisdictions." At typical in-season volume, 37 of 52 *pass*. The two figures can only be reconciled if the original diagnosis counted state-**weeks** pooled across the full season including shoulders, where volume is far below the in-season median — which is plausible, and is precisely why the rule below is per-cell rather than per-state. Worth resolving before the run, because it changes the expected size of the prize: **the eligible set includes CA, TX, OH, WI, PA, GA, NC, MI, IL, VA, WA, MA, MN, MO, NJ, AZ and MD**, i.e. most of the WIS mass. The conspicuous hole is NY, which has no typed data at all rather than thin typed data, so no threshold can recover it.

**Eligibility rule (pre-register exactly this, do not tune it).** For state *s* and forecast week *w*, the member is eligible iff the vintage-true `fluview_clinical` record available at *w* has a trailing-4-week median of `total_a + total_b` at least *n\**, with *n\** fixed a priori by the binomial standard-error argument: SE of the A-share is `sqrt(p(1-p)/n)`, which at *p* = 0.8 falls below 0.05 for *n* ≥ 64. Pre-register *n\** = 64 and try no alternatives. Applied per state-week, not as a hand-picked state list — a dynamic sufficiency rule is structural; a curated list is a fitted weight wearing a disguise.

**Vintage story.** Clean. I verified `fluview_clinical` returns Pennsylvania week 202502 at issue 202503, lag 1 — genuine one-week vintages, which is what an as-of eligibility computation needs.

**Free triage number to compute first, before any fitting.** The share of total baseline WIS mass falling in eligible cells. relWIS sums WIS across cells, so high-volume jurisdictions dominate — and typed-lab volume does correlate with state size, as the eligible list above confirms, so the eligible set carries far more pooled weight than its jurisdiction count suggests. If that share is below ~20%, the maximum achievable pooled movement is bounded near the noise floor and you should know that before spending 13,000 fits. Given that the eligible set contains almost every large state except NY and FL, I expect this number to come in high, which makes candidate 4.1 more attractive than the handoff implied — but it is still worth the ten minutes to compute rather than assume.

**Per-phase prediction.** Onset: neutral. Peak turn: the gain the member already demonstrated, now undiluted. Descent: neutral to slightly positive. Plateau: positive — the plateau season is where the member already beat the PF outright.

**Predicted failure mode.** Two. First, the eligible set turns out to carry little WIS mass and the pooled number moves less than 5%, i.e. a null rather than a loss. Second, and more insidious: eligibility flickers week to week as specimen counts cross the threshold, so a state's ensemble composition changes mid-season and introduces its own variance. Mitigation, pre-registered: once a state becomes eligible, it stays eligible for the rest of the season (a latching rule, decided a priori, not by score).

**Draft pre-registration.**
- Arms: A0 production 2-member 50/50; A1 3-member equal weights with the latching sufficiency rule; A2 3-member equal weights everywhere (the known-failing arm, retained as a negative control at panel scale only).
- Selection: no tuning parameters. *n\** = 64 and the latching rule are fixed by argument, not search.
- Gate 1 (turn): A1 beats production PF on Feb-2024 and Jan-2025 as-of months, paired seeds, identical cells, restricted to eligible cells.
- Gate 2 (seat): A1 beats A0 on identical full-grid cells, all seasons pooled.
- Floor: member relWIS < 1.1 in every season on eligible cells.
- Report regardless of outcome: eligible-cell WIS mass share, and the count of eligibility latches per season.

### 4.2 Age-structured two-class SIHRS with a pediatric-share channel — *rank 2*

> **Drafted and smoke-tested 2026-08-21:** `research/candidate-age2/`. The BNGL model, token derivation and integration spec are there, along with three design findings that only surfaced in testing — the NGM normalization that keeps `Reff` orthogonal to the mixing parameter, why the lead must be carried by contact intensity rather than susceptibility, and why the seed split cannot be an expression in `theta`. It also revises the sufficiency picture below: the age strata are present in **every** jurisdiction, with only 5 thin, which is a far better coverage story than this section assumed.

**Compartment sketch.** Two classes *a* ∈ {c = 0-17, d = 18+}, population fractions from census:

```
S_a' = -lambda_a S_a + omega R_a
I_a' =  lambda_a S_a - gamma I_a
H_a' =  rho_a gamma I_a - nu H_a
R_a' = (1 - rho_a) gamma I_a + nu H_a - omega R_a

lambda_a(t) = beta(t) * sum_b M_ab(theta) * I_b / N_b
beta(t)     = beta0 * exp(eps1 * cos(2 pi (t - phi1) / 52))
M(theta)    = (1 - theta) * M_prem + theta * diag(M_prem),  rescaled to leading eigenvalue 1
```

Rescaling *M* to unit spectral radius preserves the meaning of Reff, so the existing prior transfers unchanged.

**Observation model.**

```
y_total,t ~ NegBin( mult * sum_a rho_a * gamma * I_a ,  r )
y_ped,t   ~ Binomial( n = y_total,t - y_unknown-age,t ,  p_t )
p_t       = rho_c gamma I_c / sum_a rho_a gamma I_a
```

`mult`, the hospital reporting completeness, and any shared ascertainment drift all cancel in *p*. This is a stronger cancellation than NREVSS achieves, because numerator and denominator come from the *same records* rather than a parallel surveillance stream.

**Parameter discipline.** Fitted: Reff, eps1, phi1, mult, r, theta — six, one more than production, against six new observables per week. Fixed, not fitted: *M_prem* from published US contact matrices; the ratio rho_c/rho_d from FluSurv-NET age-specific rate climatology (legitimate as a fixed constant — constants need no vintages, which is exactly why FluSurv-NET's 36-52 week publication lag does not disqualify it here); N_c/N_d from census.

**Identifiability.** theta is identified by the pediatric share trajectory, which the aggregate stream cannot express at all. The triage result says the identified quantity has forward content: pediatric growth predicts adult growth one week ahead at median partial +0.315 in 2024-25.

**Specify the channel on growth, not level.** The share *level* tested null (+0.09, sign-incoherent). Within the mechanistic model this distinction is automatic — the two-class dynamics convert an early pediatric acceleration into an earlier adult turn without anyone specifying a growth statistic. But if the channel is ever approximated by a regression, use the growth form.

**Per-phase prediction.** Onset: earlier and better-calibrated, since children seed. Peak turn: the target — pediatric deceleration precedes adult deceleration, and theta converts that into an earlier turn call. Descent: neutral; pediatric counts fall, binomial *n* shrinks, channel goes quiet by construction. Plateau: the most uncertain. A two-class model *can* represent an age-sequenced double hump that the one-class model cannot, which is the upside; it can also invent one, which is the downside.

**Predicted failure mode.** Law 6, verbatim. Median weekly pediatric admissions run from about 13 (MA, NV) to 102 (OH) across the season including off-peak weeks; in the smallest jurisdictions they are single digits for most of the year, so the binomial channel is uninformative while theta is still fitted. That is the two-strain failure re-run. Design the sufficiency gate in from the start rather than discovering it on the full grid: pre-register eligibility as trailing-4-week median pediatric admissions ≥ 20, and note this is checkable from the target stream itself, so it needs no external vintage.

**The two blockers, stated plainly.**

*Season coverage.* Age strata begin week ending 2024-10-12. There is no 2023-24. The "relWIS under 1.1 in every season" floor can only be evaluated on two seasons, and the selection surface shrinks to one. Redefine the floor for this candidate a priori.

*Vintages.* There is no public vintage archive for the age columns, and I checked the three places one might exist: Delphi carries no age signals, Socrata is unversioned, and the Internet Archive holds exactly one snapshot of the CSV (2025-02-14). Options, in order of preference:

1. **Revision-stability argument plus the one snapshot.** Age strata are reported by the same hospitals on the same form as the aggregate, so late-reporting facilities contribute to all strata at once and the *shares* should revise far less than the levels. That is testable at exactly one date using the 2025-02-14 snapshot: compare as-of shares against final shares for all weeks up to Feb 2025. Pre-register a pass criterion (e.g. 90th-percentile absolute share change below 0.02) before looking.
2. **Sensitivity analysis.** Gate with final-data shares, then re-run the gate with shares perturbed by the revision distribution measured in step 1. Report both. If the verdict flips under perturbation, the candidate is not ready.
3. **Prospective archive.** Start snapshotting now (Section 6); a genuinely vintage-true gate becomes possible for 2026-27.

I want to be clear that this candidate cannot be gated to the standard the seal met. It can be gated to a documented, bounded, one-sided standard. Whether that is enough is a judgement call that should be made before the fits, not after.

**Draft pre-registration.**
- Arms: B0 production 2-member; B1 3-member equal weights with age member gated by pediatric sufficiency; B2 age member replacing the PF in eligible cells.
- Selection surface: 2024-25 only (2023-24 does not exist for this candidate). All tuning choices — the two-class cut at 18, the contact matrix source, the rho_c/rho_d source, the sufficiency threshold — fixed before any fit.
- Pre-gate: the revision-stability test above. Failing it stops the program before the grid run.
- Gate 1 (turn): B1 beats production PF on Jan-2025 turn cells (Feb-2024 unavailable), paired seeds.
- Gate 2 (seat): B1 beats B0 on identical full-grid cells across the two available seasons.
- Floor: member relWIS < 1.1 in both available seasons.
- Mandatory sensitivity re-run of Gate 2 under perturbed shares.

### 4.3 Backfill-aware likelihood — *rank 3*

**What changes.** Only the observation model. Replace

```
y_t ~ NegBin(mu_t, r)      with      y_t^(as-of, lag L) ~ NegBin(c_{s,L} * mu_t, r_L)
```

where `c_{s,L}` is the expected reporting completeness of a state-week observed at lag *L*, estimated **offline** from Delphi's versioned NHSN archive using only seasons in the selection window. No new parameters enter the per-state-week fit.

**Why it matters.** The model currently treats the freshest observation as complete. It is not. Measuring first-issue against final values across 20 states and two seasons: pooled median ratio **0.951** in 2024-25 and **0.966** in 2025-26, with 10th percentiles of 0.831 and 0.864, and roughly 40-50% of state-weeks below 0.95. The bias is strongly state-heterogeneous and therefore estimable: New Jersey and Tennessee sit at 1.000 (no revision at all), while Michigan's 2024-25 median is 0.836 and Oregon's 2025-26 median is 0.825, with 10th percentiles as low as 0.585 (AZ) and 0.610 (IL). Second-issue medians are mostly above 0.95, so this is essentially a one-week problem.

`mult` cannot absorb it: `mult` is a level parameter and this is a lag-structured bias that applies to one observation and then disappears.

**Why it targets the open gap.** An under-reported latest week looks exactly like a decelerating epidemic. During acceleration that manufactures a premature turn; during a plateau it manufactures a premature descent. Those are the January-2025 and February-2024 failure phases by name.

**Vintage story.** The best on this list, and it is the reason this candidate ranks above wastewater despite a smaller expected effect. Delphi's NHSN archive is genuinely issue-versioned back to reference week 202032, verified directly: Pennsylvania week 202502 was first published at 1,587, sat there for eight issues, jumped to 2,060 at issue 202546, and settled at 2,059. Everything this candidate needs already exists in versioned form.

**Per-phase prediction.** Onset: neutral (small counts, ratios noisy). Peak turn: the target — the filter stops over-reacting to an artificially flat last point. Descent: **possible small loss**, since during a genuine decline the under-reported point points the right way and correcting it slows the model down. Plateau: positive.

**Predicted failure mode.** Two. First, `c_{s,L}` is estimated from past seasons and reporting behaviour changes (a hospital system joins or leaves NHSN); a stale *c* introduces a systematic level bias that is worse than no correction. Mitigate by shrinking `c_{s,L}` toward the national value with a pre-registered shrinkage weight. Second, and more likely: with a median bias of 4-5% concentrated in one observation, the WIS effect may simply land under the 5% noise floor, especially at horizons 2-4. This candidate should be pre-registered with an explicit expectation that a null is the most probable outcome.

**Draft pre-registration.**
- Arms: C0 production PF; C1 PF with completeness correction, `c` estimated on seasons ≤ 2024-25; C2 as C1 but with the extra dispersion term `r_L` also lag-dependent.
- Selection: shrinkage weight and the lag depth (1 vs 2 weeks corrected) chosen on 2023-24 + 2024-25 pooled only.
- Gate 1 (turn): C1 beats C0 on Feb-2024 and Jan-2025 cells, paired seeds.
- Gate 2 (replacement): the swapped 2-member ensemble beats the production 2-member on identical full-grid cells.
- Report separately by horizon; a gain confined to h=1 is a real but small result and should not be oversold.

### 4.4 Wastewater — *rank 4, future-only*

**The arithmetic that demotes it.** Let week *w* end on a Saturday.

- NHSN preliminary publishes week *w* on the **Wednesday of week w+1** (4-day lag; verified in Delphi's source documentation and confirmed by the preliminary dataset carrying week-ending 2026-08-15 data).
- CDC NWSS updates **every Friday with the previous week's data** (CDC's own state-trend page). So the last NWSS update before the Wednesday deadline is the Friday of week *w*, which published week *w−1*.
- Therefore, at submission time you hold admissions through week *w* and wastewater through week *w−1*. **Wastewater is one week staler than the target it is supposed to lead.**

The influenza-specific literature puts the biological lead at 0-2 weeks and not consistently positive: wastewater peaks preceded hospitalization peaks "by 2 weeks or less" in the 2022-23 national analysis of wastewater solids ([Environ. Sci. Technol.](https://doi.org/10.1021/acs.est.3c07526)); a 2-week lead but *no* Granger-causal relationship for influenza specifically in a 50-state analysis ([Open Forum Infect. Dis.](https://doi.org/10.1093/ofid/ofaf695.190)); and wastewater *lagging* clinical measures by about one week in Cook County ([PMC10913165](https://pmc.ncbi.nlm.nih.gov/articles/PMC10913165/)). Net of the publication penalty, expected usable lead is approximately zero — which is what my triage measured directly (+0.19/+0.38 idealised, collapsing to −0.05/+0.11 at the real cadence).

**The vintage blocker, separately.** All 319,176 rows of `ymmh-divb` carry a single `date_updated` equal to the dataset's last refresh. There is no per-record publication timestamp, so as-of reconstruction is impossible. The best available substitute is a *conservative pseudo-vintage*: admit only samples with `sample_collect_date` at or before the Friday-cadence cutoff. That is one-sided in the safe direction on arrival timing, but it still leaks the site roster (you know which sites will eventually report) and any retrospective value corrections. It cannot meet the seal's standard.

**If it is ever built, build it as a growth channel.** Not a level. `r_ww(t) = median over sites of log(C_t / C_{t-1})` on PMMoV-normalized concentrations, observed with Gaussian noise against `d log I / dt`. The per-site shedding constant, population served, and site-roster composition all cancel in the per-site ratio before aggregation, which is the ascertainment-cancelling form Law 3 asks for. A level channel would need an absolute shedding-to-infection constant that nothing identifies.

**One structural prerequisite nobody has mentioned.** The current observation model has admissions instantaneously proportional to *I*. In that model a wastewater channel on *I* is, definitionally, a concurrent duplicate of the admissions channel — the ED trap by construction, no matter how good the data is. For wastewater to express a lead at all, the model must first grow an explicit pre-admission delay so that wastewater reads *I* while admissions read a lagged hospitalization inflow. That is a real modelling change that must precede the channel, and its cost should be charged to the wastewater program.

**Revival trigger, pre-registered now so it is not re-litigated.** Rebuild this candidate if and only if a state-level influenza wastewater feed becomes available **within the same publication week as NHSN preliminary**. Candidates to monitor: state health department feeds that bypass the CDC Friday roll-up (California's CalSuWers among others), or a cadence change at NWSS. WastewaterSCAN is not a substitute — it carries influenza A and B and H1/H3/H5 markers, but research use requires written permission from the Stanford/Emory team, which is a licensing dependency I would not put under a weekly submission pipeline.

**Meanwhile:** start archiving `ymmh-divb` weekly (Section 6). That costs nothing and is the only way a future gate becomes honest.

### 4.5 Fixed-coefficient importation coupling — *rank 5*

**Mechanism.** Keep per-state fitting; add an exogenous importation hazard computed from other states' vintage-true per-capita admissions:

```
lambda_s(t) = beta_s(t) I_s / N_s  +  iota * sum_{s' != s} w_{ss'} * A_{s'}(t) / N_{s'}
```

with `w` fixed from population-weighted adjacency or commuting flows and **iota fixed a priori, not fitted**. Zero new fitted parameters. This is the deliberate answer to the RW-beta lesson: add structure, not flexibility.

**Vintage story.** Clean — it uses only the target stream, which is versioned.

**Cost.** Negligible; no change to the per-state-week fitting budget.

**Predicted failure mode, and why this ranks fifth.** The seasonal envelope already makes every state turn at roughly the same time, so a national or neighbour term is largely collinear with `eps1` and `phi1`. Expect either no effect (if iota is small) or a degraded seasonal fit (if iota is large), with the plausible gain confined to onset timing in late-onset states — and onset is not the stated open gap. Worth a panel-scale look only if candidates 1-3 stall.

### 4.6 Occupancy-ratio channel — *tested and rejected*

Documented in Section 2. Raw correlation −0.75 with contemporaneous growth across 53 jurisdictions; partial correlation with next-week growth −0.03. It restates what the filter already computes.

One incidental finding worth recording for whoever builds anything on NHSN prevalence: the prevalence field is a **Wednesday snapshot**, and in the 2024-25 season Christmas Day and New Year's Day both fell on Wednesdays. The ratio shows a sharp artificial dip in those two weeks in every state I inspected (Pennsylvania: 0.267 and 0.390 against a 0.30-0.42 seasonal range). Holiday snapshot artifacts land immediately adjacent to the January turn.

### 4.7 Statistical member — *last resort, with a condition*

The brief is right that this is the cheapest diversification and that family-diverse ensembles topped the 2023-24 field. I am not recommending it, because three mechanistic directions above are live and one of them (4.1) is nearly free. But I would change that recommendation under a specific condition: **if the per-cell oracle over the two current members is already near its ceiling in the phases where you are losing.** The brief reports the oracle at 0.737 pooled and 0.814 in Jan-2025 cells — meaning that in the turn phase, even perfect per-cell selection between the two existing members leaves 18% on the table against the baseline. That gap cannot be closed by reweighting; it needs a member whose *errors are shaped differently*, and a quantile-regression member on vintage-true admissions is the cheapest way to buy differently-shaped errors. If candidates 1-3 all return nulls, that is the evidence that the mechanistic family is exhausted for this target and the statistical member should be built.

---

## 5. What I would not do

- **Do not build an age model with three or more classes.** The pediatric/adult split is where the lead lives; finer strata multiply parameters against counts that are single digits in half the grid.
- **Do not use FluSurv-NET as a channel.** As a source of fixed priors it is excellent. As a real-time observable it publishes 36-52 weeks late.
- **Do not fit iota, theta, or any coupling strength on past-season scores.** Law 1.
- **Do not gate anything on a panel.** Law 2. Everything above is specified against the full grid.

---

## 6. Actions worth taking this week regardless of what gets built

All three unblock 2027 gating and cost roughly nothing.

1. **Snapshot NHSN weekly, both datasets.** `ua7e-t2fy` (final, Friday) and `mpgq-jmmr` (preliminary, Wednesday), full CSV, tagged by retrieval date. This is the only way age strata, prevalence, and reporting-hospital counts ever become vintage-capable. Roughly 15-30 MB per snapshot.
2. **Snapshot NWSS `ymmh-divb` weekly.** Same reasoning. About 13 MB compressed for the seasons of interest.
3. **Pull the one Internet Archive snapshot** (`web.archive.org/web/20250214121605/https://data.cdc.gov/api/views/ua7e-t2fy/rows.csv`) and run the age-share revision-stability test in Section 4.2 against final data. This is the pre-gate for candidate 2 and it can be done today.

If these had been running since November 2024, candidate 2 would be gateable to the seal's standard today. Starting them now is what makes that true in fifteen months.

---

## Appendix: what was checked, and how

All checks run 2026-08-21.

**CDC Socrata (`data.cdc.gov`)**
- `ymmh-divb` (NWSS influenza A): row count and date range; `date_updated` cardinality (one distinct value over all 319,176 rows); site and jurisdiction counts by season window; sample-level pull of `pcr_target_mic_lin`, `population_served`, `pcr_target_detect` for 2023-09-01 to 2026-05-01 (248,930 rows).
- `ua7e-t2fy` (NHSN HRD, final): full column list; earliest and latest week with non-null `numconfflunewadmped0to4` (2024-10-12 to 2026-08-15, 6,419 rows, 67 jurisdictions, seasons 2024-2025 and 2025-2026 only); the same for `totalconfflunewadm` (2019-2020 onward) and `totalconffluhosppats` (2020-2021 onward); admissions, prevalence and reporting-hospital counts for the Jan-2025 turn.
- `mpgq-jmmr` (NHSN HRD, preliminary): confirmed it carries flu age strata, prevalence and reporting-hospital counts, with the same 2024-10-12 start.

**Delphi Epidata (`api.delphi.cmu.edu`)**
- `covidcast` source `nhsn`: full signal list (12 signals, no age strata); `as_of` behaviour (must be an epiweek — a date-formatted `as_of` is silently ignored and returns the latest issue, which is a trap); full issue history for PA week 202502; first-issue-vs-final ratios for 20 states across two seasons.
- `flusurv`: issue and lag structure for CA across 2024-25 (single issue at lags 36-52).
- `fluview`: state-level ILINet age fields are null (so no state-level age from ILINet).
- `fluview_clinical`: PA week 202502 at issue 202503, lag 1 — genuine one-week vintages.
- *Note:* Delphi rate-limits anonymous clients (HTTP 429) at roughly 60 requests per hour, and the block persists for some time after it trips. No API key is needed to get around it — `fluview_clinical` accepts a **comma-separated region list**, so the whole 52-jurisdiction sweep is 3 requests (one per season range) rather than 156. The eligible-jurisdiction list in §4.1 was completed this way on 2026-08-21. Any probe against this API should batch regions and should fail loudly on 429: a retry loop that swallows the exception reports rate-limiting as "this jurisdiction has no data," which is how an earlier run produced 52 rows of zeros and exit code 0.

**GitHub (`cdcepi/FluSight-forecast-hub`)**
- `auxiliary-data/` contents; `target-data-archive/` holds 117 entries — weekly `target-hospital-admissions_*.csv` vintages plus `target-ed-visits-prop_*.csv` from 2025-11-15. Aggregate target only; no age strata.

**Internet Archive**
- CDX query for `data.cdc.gov/api/views/ua7e-t2fy/rows.csv`: exactly one snapshot, 2025-02-14.

**Literature consulted for the wastewater lead time**
- [Environ. Sci. Technol. 2024, 10.1021/acs.est.3c07526](https://doi.org/10.1021/acs.est.3c07526) — 163 plants, 33 states, 2022-23; wastewater peak precedes hospitalization-rate peak by 2 weeks or less.
- [Open Forum Infect. Dis., 10.1093/ofid/ofaf695.190](https://doi.org/10.1093/ofid/ofaf695.190) — 50 states, 2021-2025; 2-week lead for influenza by cross-correlation, but no Granger-causal relationship for influenza (unlike RSV and COVID-19).
- [Cook County, IL, 2022-23 (PMC10913165)](https://pmc.ncbi.nlm.nih.gov/articles/PMC10913165/) — wastewater *lagged* traditional surveillance by about one week.
- [EID 30(8), Michigan/Ontario](https://wwwnc.cdc.gov/eid/article/30/8/24-0225_article) — strong correlation with hospitalizations; lead/lag varies by catchment.

Analysis scripts used for the triage were written to a scratch directory outside the repository and are not part of this deliverable.
