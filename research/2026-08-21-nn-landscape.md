# Neural networks for FluBNF: a landscape briefing

**Date:** 2026-08-21
**Scope:** literature and competition-evidence review. No code written; no repository files modified except this one.
**Question asked:** "multi-input neural networks, maybe some that have proven to do well in epi forecasting" — are they worth pursuing as a third ensemble member?

Every performance number below is quoted from a named published source and is cited. Where I am reasoning rather than citing, the paragraph says so explicitly. Section 8 lists what I could not verify.

---

## 0. Verdict

**No. Do not build a neural member.** Not as a stretch goal, not as a research spike. The recommendation is not "neural networks are bad"; it is that on this exact task — 23-quantile, 1–4 week, 50-jurisdiction influenza hospital admissions, scored by relWIS, under vintage-true evaluation — the published evidence does not contain a single neural network that has beaten the FluSight ensemble, and the machine-learning models that *have* won are all tree-based quantile regression, not neural.

Three findings drive this, in descending order of force.

**1. Across four hospital-admissions FluSight seasons, no neural network has topped the field.** The models that won or placed at the top were: a basic quantile autoregression (CMU-TimeSeries), a mechanistic compartmental model (MOBS-GLEAM_FLUH, PSI-DICE), and gradient-boosted quantile regression (UMass-flusion, MIGHTE-Nsemble). The 2023-24 winner, Flusion, is LightGBM. The one AI/ML-tagged model in 2022-23 that was *purely* AI/ML — VTSanghani-ExogModel — scored relWIS 0.98 with 50% interval coverage of 30% against a nominal 50%. Details and citations in §2.

**2. FluBNF's actual defect is the one a neural member would make worse.** The brief states the predictive distribution is too wide, not that the median is wrong. Flusion — the best documented multi-source ML model on this exact target — was itself *underconfident*, with 95% coverage of 96.3% against a nominal 95% and intervals "too wide on average" ([Ray et al., *Epidemics* 2025](https://doi.org/10.1016/j.epidem.2024.100810)). Because equal-weight quantile averaging makes the ensemble's interval width the arithmetic mean of its members' interval widths (§5.4), adding a member that is wider than the current ensemble *arithmetically guarantees* a wider ensemble. A neural member would need to be both sharper and calibrated, and the literature does not show neural models being sharper here.

**3. The single most relevant recent result in this literature is a leakage retraction, and it is precisely this team's documented failure mode.** A 2026 *Nature* paper claimed an AI system beat the CDC ensemble on COVID hospitalisations by 11% WIS. [Bracher & Funk](https://arxiv.org/html/2608.05883) showed that essentially the entire gain was information leakage from unmodelled data revisions: in the state-weeks where the last observation was *not* revised, the relative WIS was 1.00 — dead level with the ensemble. All of the apparent advantage lived in the revised bins. This is the ED-signal failure in a new costume, and it is the default outcome of any retrospective NN evaluation that is not vintage-true.

**What I would do instead.** If the team wants a third member from *this* literature rather than from the mechanistic directions already queued in [the member-search memo](2026-08-21-member-search-memo.md), the defensible option is a gradient-boosted quantile regression member trained jointly across jurisdictions and across long-history auxiliary signals — a "Flusion-lite". It is not neural, it needs no fitted ensemble weights, it emits 23 quantiles natively, and it is the only ML family with a documented FluSight win. I still rank it *below* the memo's candidate 4.1 (two-strain with a sufficiency gate), for reasons given in §6.

**On the `einn` stub in `app/core/runs.py`.** EINN is a real, peer-reviewed method (AAAI-23) from a serious group. It is nonetheless not a credible FluBNF member, primarily because *it does not produce quantiles at all* — it is evaluated on normalised RMSE and Pearson correlation, and its influenza experiment covers 10 HHS regions for 5 months. §1 gives the full assessment. My recommendation is to delete the `| 'einn'` from that comment or replace it with a note pointing here, so that a future reader does not mistake an aspiration for a plan.

---

## 1. What EINN actually is, and whether it is credible

**Reference:** Rodríguez, Cui, Ramakrishnan, Adhikari & Prakash, "EINNs: Epidemiologically-Informed Neural Networks", *AAAI* 37(12):14453–14460, 2023. [doi:10.1609/aaai.v37i12.26690](https://doi.org/10.1609/aaai.v37i12.26690) · [PDF](https://ojs.aaai.org/index.php/AAAI/article/download/26690/26462)

**In the codebase.** `einn` appears exactly once, in a docstring comment on `RunSpec.engine` in `app/core/runs.py`. There is no engine module, no dispatch branch, no test. It is an aspiration, correctly diagnosed.

**What the method is.** A two-model transfer-learning setup. A physics-informed neural network (the "time module") takes time as its only input and learns latent epidemic dynamics by matching the gradients of an SEIRM/SIRS ODE system, without numerically integrating it. Those learned representations are transferred, via a gradient-matching loss, into a feature-ingesting RNN (the "feature module") that consumes heterogeneous exogenous signals. The motivation is real and well-posed: RNNs produce forecasts poorly correlated with epidemic trend shape; mechanistic models capture shape but ingest few signals.

**Why it is credible as research.** The authors are the group behind DeepCOVID and multiple CDC-hub submissions. The gradient-matching formulation is a genuine contribution, and the paper is honest that it defines its own problem.

**Why it is not a credible FluBNF member.** Five concrete blockers, all from the paper itself:

| Blocker | Evidence from the paper |
|---|---|
| **No quantiles.** This is disqualifying on its own. | Metrics are two variants of normalised RMSE, Normal Deviation, and Pearson correlation. There is no WIS, no interval score, no coverage, no calibration analysis anywhere in the paper. FluSight requires 23 quantiles; EINN as published emits a point forecast. |
| **The influenza experiment is tiny.** | "flu (in 10 regions and 5 months)" — HHS regions, not the 50-state grid. The team's Law 2 (panel results do not transfer to the full grid) applies with full force, and 10 HHS regions is a *coarser* panel than a 10-state panel. |
| **No baseline anyone else recognises.** | "As we are the first to pose the INCORPORATING EPI-DYNAMICS IN NNS problem, we do not have off-the-shelf baselines." Comparators are the authors' own ablations (GENERATION, REGULARIZATION, ENSEMBLING) plus a plain RNN and the mechanistic model. There is no comparison to a FluSight baseline, a hub ensemble, or any hub submission. A relWIS number for EINN does not exist. |
| **No vintage discipline.** | The paper does not mention data revisions, backfill, issue dates, or as-of queries. Given §5.2, the reported gains have unknown status under vintage-true evaluation. |
| **The flu inputs are Google symptom search data.** | "For flu, we use the 14 signals from the Google symptom dataset." See §7 on why that particular channel carries the heaviest documented cautionary history in this field. |

**The telling detail.** The same lab (Prakash, Georgia Tech) *does* submit to FluSight — as `GT-FluFNP`, which appears to be the hub deployment of EpiFNP, their calibration-focused neural process model ([Kamarthi et al., NeurIPS 2021](https://arxiv.org/abs/2106.03904)). They submitted the calibrated neural model, not EINN. That is a revealed preference worth respecting. GT-FluFNP's hub record is in §2 and is the best documented neural result in FluSight — relWIS 1.03 in 2021-22 and 0.81 in 2022-23, i.e. worse than the baseline once and better than the baseline but worse than the ensemble once.

*(Inference, not citation: I am reading the GT-FluFNP ↔ EpiFNP link from the name, the lab, and the timing. I could not find a metadata file stating it. See §8.)*

---

## 2. Competition evidence

### 2.1 FluSight 2021-22 and 2022-23 (peer-reviewed)

Mathis et al., "Evaluation of FluSight influenza forecasting in the 2021–22 and 2022–23 seasons…", *Nature Communications* 15:6289 (2024). [doi:10.1038/s41467-024-50601-9](https://doi.org/10.1038/s41467-024-50601-9)

Columns are as published in Table 1: relative WIS against the FluSight baseline, then empirical coverage of the 50% and 95% prediction intervals (nominal 50 and 95). Type tags are CDC's own. Only models at or below baseline are listed in full, plus the neural entrants.

**2021-22 — 6 of 23 models beat the baseline.**

| Model | Type | relWIS | 50% cov | 95% cov |
|---|---|---|---|---|
| CMU-TimeSeries | STAT | **0.74** | 47 | 90 |
| FluSight-ensemble | ENS | 0.82 | 48 | 86 |
| PSI-DICE | MECH | 0.83 | 43 | 82 |
| UMass-trends_ensemble | ENS | 0.85 | 71 | 97 |
| SGroup-RandomForest | ENS | 0.91 | 47 | 95 |
| CEID-Walk | STAT | 0.93 | 52 | 82 |
| *FluSight-baseline* | STAT | *1.00* | 49 | 83 |
| GT-FluFNP | STAT (tagged) | 1.03 | 39 | 69 |

**2022-23 — 12 of 18 models beat the baseline.**

| Model | Type | relWIS | 50% cov | 95% cov |
|---|---|---|---|---|
| MOBS-GLEAM_FLUH | MECH | **0.61** | 42 | 78 |
| CMU-TimeSeries | STAT | 0.67 | 49 | 87 |
| PSI-DICE | MECH | 0.70 | 48 | 80 |
| MIGHTE-Nsemble | ENS, AI/ML, STAT | 0.73 | 53 | 82 |
| FluSight-ensemble | ENS | 0.77 | 56 | 81 |
| UMass-trends_ensemble | ENS | 0.80 | 63 | 89 |
| GT-FluFNP | STAT (tagged) | 0.81 | 56 | 75 |
| SGroup-RandomForest | ENS | 0.82 | 53 | 84 |
| CU-ensemble | ENS | 0.83 | 51 | 70 |
| CEPH-Rtrend_fluH | STAT | 0.84 | 44 | 78 |
| UGA_flucast-OKeeffe | STAT | 0.93 | 50 | 72 |
| VTSanghani-ExogModel | **AI/ML** | 0.98 | **30** | **61** |
| *FluSight-baseline* | STAT | *1.00* | 49 | 74 |

Five things in these tables matter for FluBNF.

- **The winner both seasons was a quantile autoregression.** CMU-TimeSeries was the only model to beat the FluSight ensemble in *both* seasons. The paper describes the sub-1.0 group as "a basic quantile autoregression fit, a mechanistic compartmental model with stochastic simulations, an ensemble of time-series baseline models, a random walk model, a random forest ensemble, and the FluSight ensemble." No neural network appears in that list either season.
- **The only pure AI/ML model was the worst-calibrated model in the table.** VTSanghani-ExogModel achieved 30% empirical coverage on its 50% intervals and 61% on its 95% intervals. That is severe overconfidence, and it is the opposite of FluBNF's current defect — which is a reason for caution, not encouragement: swapping "too wide" for "far too narrow" is not an improvement, and §5.3 explains why this direction of miscalibration is the *normal* one for neural quantile models.
- **The best AI/ML-tagged result is gradient boosting.** MIGHTE-Nsemble (relWIS 0.73, beat the ensemble) is described by its team as a "weighted ensemble of time-series models, including lightGBM with hyperparameters tuned over the previous season… and ARIMA models" ([Epistorm model listing](https://www.epistorm.org/activities/flu-forecast)). Trees, not neurons.
- **Nobody is well-calibrated at 95%.** "Almost all models (with the exception of the UMass trends ensemble) were overconfident in their predictions." The FluSight ensemble's own 95% coverage fell from 89.6% to 83.7% (2021-22) and 85.7% to 77.9% (2022-23) across horizons 1→4.
- **The turn is everyone's open problem, not FluBNF's alone.** "The only model that had 95% coverage greater than 80% from October to January 2023 when hospitalizations were rapidly increasing and then peaking was LUCompUncertLab-humanjudgment" — a human-judgment model, which then failed the season inclusion criteria. That is the state of the art on the turn phase.

### 2.2 FluSight 2023-24 — the multi-source model that won, and what actually made it win

[CDC FluSight 2023-2024 Evaluation](https://www.cdc.gov/flu-forecasting/evaluation/2023-2024-report.html): 28 teams, 36 models, 28 met inclusion. **The FluSight ensemble beat 27 of the 28. The single model that beat it was UMass-flusion.**

Flusion is documented in Ray et al., "Flusion: Integrating multiple data sources for accurate influenza predictions", *Epidemics* 50:100810 (2025). [doi:10.1016/j.epidem.2024.100810](https://doi.org/10.1016/j.epidem.2024.100810) · [arXiv](https://arxiv.org/abs/2407.19054) · [code](https://github.com/reichlab/flusion)

This is the most directly relevant paper in the entire literature for FluBNF, and it deserves close reading — but read for what it actually says, because it is easy to misread as an endorsement of multi-input models.

**What Flusion is.** An equal-weight quantile average of three components: two LightGBM quantile-regression models (GBQR) with different feature sets, and a Bayesian autoregressive model with a Christmas-week covariate. It uses three signals: NHSN admissions (the target), FluSurv-NET hospitalisation rates, and ILI+ (ILINet × NREVSS test positivity).

**The ablation, which is the load-bearing result** (Table 3; rMWIS relative to the flat baseline, state-level, horizons 0–3, 2023-24):

| Variant | rMWIS | What changed |
|---|---|---|
| Flusion (full) | 0.622 | — |
| GBQR alone | 0.625 | drop the ensemble |
| GBQR-by-location | **0.780** | train separately per jurisdiction |
| ARX alone | 0.815 | classical AR only |
| GBQR-only-NHSN | **0.857** | drop the auxiliary signals |
| Baseline-flat | 1.000 | — |

The authors' conclusion: "this strong performance was primarily driven by the use of a gradient boosting model that was trained jointly on data from multiple surveillance signals and multiple locations… forming predictions as an ensemble… yielded only a small gain."

**The crucial nuance, and the reason this does not endorse the user's instinct.** The extra signals are *not* used as contemporaneous predictors. They are used as **extra training rows**. The paper is explicit:

> "predictions of NHSN admissions in a particular location were not informed by contemporaneous observations of NHSN admissions in other locations or by contemporaneous observations of other surveillance signals in that same location. The use of contemporaneous observations from other locations or signals to inform predictions remains a topic for future work."

So the winning "multi-source" model is a *transfer-learning* model, not a multi-input model. FluSurv-NET and ILI+ supply twenty-odd extra pseudo-seasons of "what does a flu season shaped like this do next", solving a **data-volume** problem. They do not supply a leading indicator. The user's stated instinct — "multiple predictors plopped into a NN to learn the relationships" — is the thing Flusion explicitly did *not* do and listed as future work.

**Two more findings from this paper that should change priors here.**

- **The reporting adjustments were counterproductive.** GBQR-no-reporting-adj (raw ILI, raw FluSurv-NET, no burden-based inflation) scored 0.600, *better* than the adjusted GBQR at 0.625. Careful epidemiological correction of the auxiliary signals actively hurt.
- **Flusion was too wide, like FluBNF.** 50% coverage 0.558, 95% coverage 0.963; "prediction intervals from Flusion tended to be underconfident, i.e., prediction intervals were too wide on average." Its calibration was still better than the baseline's and the ensemble's — but it does not solve the width problem, it shares it.

### 2.3 FluSight 2024-25 — and the noise-floor result

[CDC FluSight 2024-2025 Evaluation](https://www.cdc.gov/flu-forecasting/evaluation/2024-2025-report.html): 33 teams, 46 models, 35 met inclusion. **The FluSight ensemble outperformed every submitted model.** Best individual was PSI-PROF_beta. 27 of 36 beat the baseline.

Two facts here bear directly on FluBNF's decision rule:

- **"The top 10 performing models had similar relative WIS values, with the top 10 all falling within 0.04 of each other."** This is independent, external confirmation of the team's own ~5% noise-floor discipline. At the top of this leaderboard, the difference between rank 1 and rank 10 is smaller than the movement FluBNF can reliably detect. A new member that is merely competitive is, by construction, undetectable.
- **January 2025 broke everyone.** "The lowest coverage for the FluSight ensemble occurred on January 4, 2025… with just 6% of the 2-week horizon forecast prediction intervals across jurisdictions containing observed values." CDC withheld public forecast publication until 5 March 2025. FluBNF's open problem — the January 2025 turn — is the same turn that reduced the CDC ensemble to 6% coverage. Anyone claiming a member that fixes it should be asked for extraordinary evidence.

### 2.4 Ten seasons, pooled

[Prasad/CDC FluSight team, "A Decade of CDC FluSight Influenza Forecasting", medRxiv 2026](https://www.medrxiv.org/content/10.64898/2026.06.05.26354941v1.full-text) (preprint, not peer reviewed).

- ML models grew from 17% of submissions in the ILI era to **29% in the hospital-admissions era** — so the absence of neural winners is not an absence of neural attempts.
- **"For influenza hospitalization seasons, no significant differences in model performance were observed within individual seasons or pooled seasons"** across statistical / mechanistic / ML / hybrid categories.
- Across 11 seasons: statistical models ranked first in five, mechanistic in three, FluSight ensembles in two, and machine-learning and statistical/mechanistic hybrids **once each**. The single ML first place is UMass-flusion — gradient boosting.
- In the ILI era, statistical models significantly outperformed ML models in 2019/20 (p < 0.05).

The honest summary of a decade: **model family does not predict performance on this target.** Nobody has shown that buying a neural network buys skill.

### 2.5 The COVID-19 Forecast Hub

Cramer et al., *PNAS* 119(15):e2113561119 (2022). [doi:10.1073/pnas.2113561119](https://doi.org/10.1073/pnas.2113561119)

27 models with complete submissions, April 2020 – October 2021. The COVIDhub-ensemble achieved relWIS 0.61 and was the most consistently accurate model; 18 of 27 beat the baseline; "different models showed the highest accuracy overall" in different pandemic phases. The paper's headline finding — high variability between and within individual models, consistent accuracy only from the ensemble — is the same result as FluSight's, on a different pathogen with far more data.

**Relevance to FluBNF:** this is the strongest available evidence for the team's Law 1. Across two hubs and six years, the thing that reliably works is combining structurally different models under simple, unfitted combination rules. Nothing in either hub's history supports fitted weights, and nothing supports a particular architecture.

### 2.6 The one genuine recent AI success — reported accurately

Martinson et al., "Prospective multi-pathogen disease forecasting using autonomous LLM-guided tree search", [arXiv:2605.16238](https://arxiv.org/abs/2605.16238) (2026, preprint).

I include this because omitting it would be dishonest: it is the strongest pro-AI result in this literature and it is *methodologically clean*.

Google Research's ERA system used LLM-guided Monte Carlo tree search to generate forecasting code. In a **fully prospective, time-stamped** 2025-26 season across FluSight, COVIDHub and RSVHub, `Google_SAI-FluEns` **ranked first among 43 eligible FluSight submissions**, ahead of the official FluSight-ensemble.

Four qualifications that matter more than the headline:

1. **It is not a neural network.** It is an LLM writing conventional forecasting code, then an equal-weight ensemble of 19 of those programs. The forecasting models themselves are compartmental, statistical and gradient-boosted.
2. **The two ERA component models that individually beat the FluSight ensemble were mechanistic/statistical hybrids** — an adaptation of Cornell_JHU-hierarchSIR, and a recombination of LANL-DBM (SIR + statistical discrepancy term) with LANL-Inferno (Bayesian). Not neural.
3. **The system had to be actively steered away from ML defaults.** "ERA, when operating without explicit methodological instructions, exhibits a systematic bias toward modeling approaches that are heavily represented in LLM training corpora — most notably gradient-boosted trees, random forests, and similar standard machine learning regressors," and the authors added instruction-following gates because "the historical strength of CDC hub ensembles derives precisely from their methodological diversity."
4. **The cost was 142 prompts and over 207,500 candidate models**, narrowed to 54, then 19. This is not a route available to FluBNF.

**And the same system is the subject of §5.2's leakage retraction.** The predecessor study ([Aygün et al., *Nature* 654:909–916, 2026](https://doi.org/10.1038/s41586-026-10658-6)) claimed an 11% WIS improvement retrospectively; that claim did not survive vintage-correct re-analysis. The prospective result stands because it was prospective. The lesson FluBNF should take is not "AI works" but **"the only version of this result that survived was the one with auditable time stamps."**

---

## 3. Architecture comparison

Data requirements below are stated in terms of FluBNF's actual corpus: **~3 seasons × ~26 in-season weeks × ~52 jurisdictions ≈ 4,000 state-week observations**, of which the effective independent sample is far smaller — with strong within-state autocorrelation and near-total cross-state correlation through the shared seasonal envelope, the number of independent "season shapes" is closer to **3 × (a handful of distinct regional patterns)**, not 4,000. This distinction is the whole ballgame and is discussed in §5.1.

"Native quantiles" means the architecture emits calibrated quantile levels from its own loss, without a post-hoc wrapper.

| Family | Representative | Rough data need | Native 23 quantiles? | Feasible at FluBNF's volume? | Hub track record on this target |
|---|---|---|---|---|---|
| **Gradient-boosted quantile regression** | LightGBM + pinball loss (Flusion GBQR, MIGHTE) | Works at 10²–10³ rows; degrades gracefully | **Yes** — one fit per quantile level, sorted post hoc | **Yes.** The only ML family demonstrated at this volume | **Won 2023-24 (Flusion); beat ensemble 2022-23 (MIGHTE)** |
| **Quantile autoregression** | CMU-TimeSeries | 10² rows | **Yes** | Yes | **Best model 2021-22 and 2022-23** |
| **Small recurrent (LSTM/GRU)** | TinyLSTM | 10³–10⁴ sequences for a normal LSTM; a *deliberately tiny* one can work lower | Only via pinball-loss head or MC dropout; not by default | Marginal — only in heavily regularised, few-unit form | None at the top of FluSight |
| **Seq2seq / attention** | Vanilla Transformer, Autoformer | 10⁴–10⁵ sequences | Via quantile head | **No.** Documented to be data-starved here | None |
| **Temporal Fusion Transformer** | [Lim et al., IJF 2021](https://arxiv.org/abs/1912.09363) | 10⁴–10⁵ | **Yes** — quantile regression is built in, and it explicitly separates static / known-future / observed-past covariates | **No** at 3 seasons. Architecturally the best fit for the multi-input question, and the least fundable by the data | None in FluSight |
| **DeepAR** | [Salinas et al.](https://arxiv.org/abs/1704.04110) | 10³–10⁴ related series | Parametric likelihood → sample quantiles | Marginal; parametric family choice becomes the dominant modelling assumption | None in FluSight |
| **N-BEATS / N-HiTS** | Oreshkin et al.; Challu et al. | 10⁴+ | No (point forecasts; intervals need ensembling) | **No**, and no quantiles | None |
| **Graph neural networks** | spatial coupling across jurisdictions | 10⁴+ plus a defensible graph | No | **No.** And FluBNF's own memo predicts a spatial coupling term is collinear with the seasonal envelope (candidate 4.5) | None |
| **PINN / EINN** | [EINN, AAAI-23](https://doi.org/10.1609/aaai.v37i12.26690) | Per-region fit; modest data | **No** — RMSE/correlation only | **No**, on the quantile blocker alone | None; never submitted |
| **Neural ODE** | latent ODE hybrids | 10³+ | No | No | None |
| **Foundation TS models (numerical)** | TimesFM, TabPFN-TS, Chronos | Zero-shot; no training data needed | Some emit quantiles natively | **Technically yes** — the only NN-adjacent option that clears the volume bar, because it needs no training | None in FluSight; see §4 |
| **LLM-style TS models** | TimeLLM, Chronos-T5 | Zero-shot | Sampling-based | Yes, but documented to underperform | Documented **worse** than numerical models on this exact task |

### Blunt assessment of infeasibility

At 3 seasons of NHSN history, **TFT, N-BEATS/N-HiTS, DeepAR, GNNs, and any full-size Transformer are not fundable**, full stop. TFT is the architecture that most directly answers "multi-input NN" — it has a variable-selection network and native quantile regression — and it is the one that most obviously cannot be trained here. TFT's published benchmarks are electricity, traffic and retail: tens of thousands of series, years of high-frequency history. FluBNF has three seasons.

This is not my opinion; it is measured. The most relevant benchmark I found ([Jafari et al., arXiv:2606.19560](https://arxiv.org/abs/2606.19560), preprint) ran exactly this comparison on CDC-aligned 1–4-week influenza *hospitalisation* forecasting with "only about three years of weekly hospitalization data" — the same regime FluBNF is in. Their finding:

> "Among models that use only hospitalization, TinyLSTM achieves the lowest average error (0.00262). iTransformer and PatchTST remain competitive (0.00345 and 0.00361), while TimeLLM is clearly weaker (0.00595). This ordering contrasts with the ILI experiments, where large, high-capacity foundation-style architectures often dominate: here, with only three years of data, a smaller recurrent model (TinyLSTM) provides the strongest pure-hospitalization baseline."

Read that carefully. **The result of doing this properly at three seasons of data is that the winning neural architecture is a deliberately crippled LSTM with a few recurrent units.** That is the ceiling. It is also MSE on HHS regions, not WIS on 50 states (see §8).

A European ILI benchmark reaches the same conclusion from the other direction ([Wang, Li & Perra, medRxiv 2026](https://www.medrxiv.org/content/10.64898/2026.05.11.26352889v1.full-text), preprint): "deep learning architectures are severely constrained by extreme data scarcity, typical in epidemic forecasting… simpler architectures (such as DLinear and LSTM) frequently exhibit greater robustness and outperform complex, attention-based models (such as Autoformer) when data is constrained." *Caveat: this is one of the papers Bracher & Funk name as underestimating revision-driven leakage.*

---

## 4. Transfer learning, pretraining and foundation models

The user asked specifically whether pretraining offers a credible route. Three sub-answers.

**(a) Transfer from long-history influenza signals: yes, and it is the proven lever.** This is exactly what Flusion did, and the ablation says it was worth 0.857 → 0.625 in rMWIS. It is also what CMU-TimeSeries does — "the data are whitened so that the historical flusurv and ILI data can be used to augment the number of training examples" — and what the ERA system was prompted to do, with ~20 years of ILINet supplied as augmentation. **Every top model on this target solves the data-volume problem the same way, and none of them do it with a neural network.**

For FluBNF this is genuinely encouraging, because the team already has a vintage-true NREVSS layer (`flubnf/nrevss.py`, `fluview_clinical`, verified lag-1 issues) and the memo confirms Delphi serves `fluview` and `flusurv` histories. The infrastructure for a Flusion-lite exists.

**(b) Transfer from other pathogens or countries: thin.** Flusion's authors note "the literature contains only a few applications of this general approach to disease outbreak forecasting." The Jafari benchmark reports that "pretraining provides the largest gains at longer horizons, particularly when the pretraining domain is mechanistically aligned with influenza dynamics" — i.e. the gains come from flu-like pretraining, not from generic cross-pathogen transfer. ERA's RSV results are a warning: Deep-Research-originated architectures "largely failed for RSV forecasting, with the majority performing worse than the CDC's flat-line baseline."

**(c) Foundation models: interesting, unproven on this target, and with one specific attraction.** The published evaluations ([Bosic et al., *Epidemics* 2026, doi:10.1016/j.epidem.2026.100916](https://doi.org/10.1016/j.epidem.2026.100916); [medRxiv preprint](https://doi.org/10.1101/2025.02.24.25322795)) tested TabPFN-TS, TimeGPT, TimesFM, Lag-Llama and Chronos across ILI, RSV, chickenpox, dengue and COVID, and report "strong accuracy in short-term forecasts… outperformed standard implementations of established models on limited and irregular data."

The attraction is precise and worth stating: **a zero-shot foundation model has no training step, so it has no training-data leakage surface.** The only vintage discipline it needs is that its *context window* be a vintage-true series. That removes the single largest risk in §5.2 — although not the ground-truth-scoring half of it.

But: none has been evaluated on FluSight, none of these papers reports relWIS against the FluSight baseline on the 50-state grid, and Jafari et al. find LLM-style foundation models specifically underperform on 1–4-week influenza hospitalisations. The Bosic paper compares against "standard implementations" of traditional models, not against tuned hub submissions. Treat as a watch item, not a plan.

---

## 5. The four project-specific risks

### 5.1 Data volume — the realistic ceiling

FluBNF has ~4,000 state-week NHSN observations. That number is misleading in the direction that flatters neural networks.

*(Reasoning, not citation.)* The effective sample size for learning *season shape* — which is what a forecaster must learn — is not 4,000. It is closer to the number of independent season-trajectory realisations, which is 3 seasons × a small number of distinct regional patterns, because within a season all 52 jurisdictions ride a common seasonal envelope and are heavily cross-correlated. A model with 10⁴–10⁶ parameters facing a handful of independent season shapes will interpolate them and generalise to nothing. This is the same arithmetic Lazer et al. identified in Google Flu Trends: "the methodology was to find the best matches among 50 million search terms to fit 1152 data points… The odds of finding search terms that match the propensity of the flu but are structurally unrelated, and so do not predict the future, were quite high" ([Science 343:1203–1205, 2014](https://doi.org/10.1126/science.1248506)).

**The realistic ceiling, stated plainly.** With the target signal alone, the ceiling is a small regularised model with O(10–100) effective parameters — TinyLSTM-scale, or equivalently gradient boosting with aggressive bagging. With auxiliary long-history signals appended as training rows (Flusion's approach), the ceiling rises to roughly what Flusion achieved, because that is the demonstrated frontier of this approach on this exact target.

**Note the direct conflict with the team's parsimony law.** FluBNF's PF fits ≤6 parameters. Even a TinyLSTM is two orders of magnitude more. The brief states that extra fitted dimensions worsen the width problem. A neural member does not bend that rule, it abandons it — and would need to justify doing so with evidence that does not exist in §2.

### 5.2 Vintage-honesty — the dominant risk, quantified

This is where a neural member is most likely to produce a spurious success, and there is now a clean quantitative demonstration.

**The mechanism.** NHSN admissions are revised upward as late-reporting facilities file. The team's own memo measured this: first-issue-to-final ratios with a pooled median of 0.951 (2024-25) and 0.966 (2025-26), 10th percentiles near 0.83–0.86, and state-level medians as low as 0.836 (Michigan). A model trained on *final* data learns the relationship "this week's final value → next week's final value." At deployment it is handed a *preliminary* value that is systematically 4–5% low, and more in some states. It has never seen that input distribution.

**Why this is worse for a NN than for the particle filter.** *(Reasoning.)* The PF has an explicit observation model with a dispersion parameter; a systematically low observation is absorbed, imperfectly, as noise. A neural network has no such structure — it learns an arbitrary function of its inputs, and a shifted input distribution at test time is straightforwardly out-of-distribution. Worse, a NN trained on final data will *learn to trust the last observation more than it should*, because in the training data the last observation was always complete. During a plateau or an ascent, an under-reported last point looks exactly like deceleration. That is the February-2024 and January-2025 failure by name — so the naive version of this member would fail hardest in precisely the phase it was built to fix.

**The quantified demonstration.** [Bracher & Funk, arXiv:2608.05883](https://arxiv.org/html/2608.05883) re-analysed the *Nature* ERA COVID result. Binning 1,430 state-weeks by how much the last available observation was ultimately revised:

| Bin (relative revision of last observation) | [0%,1%] | (1%,5%] | (5%,10%] | (10%,25%] | (25%,380%] |
|---|---|---|---|---|---|
| Share of state-weeks | 20% | 21% | 20% | 22% | 18% |
| relWIS vs CDC ensemble | **1.00** | 0.92 | 0.95 | 0.90 | **0.69** |

The reported 11% advantage is entirely an artefact of the revised bins. Where there were no revisions, the model was exactly level with the ensemble. Nine state-weeks out of 1,430 accounted for 20% of the total WIS difference.

**What this implies for a FluBNF pilot.** Any retrospective NN evaluation that is not vintage-true will produce a number in the 0.85–0.95 range that means nothing. Given the memo's finding that ~40–50% of state-weeks revise by more than 5%, FluBNF's revision exposure is comparable to the COVID case. **A NN pilot that skips vintage discipline will manufacture a false positive with high probability.**

**How to do it correctly.** Both training and scoring must be version-faithful:
- *Training:* each training row's features must be the values as published at that row's reference date, not final values. This means reconstructing an as-of feature matrix for every historical reference date — for 3 seasons × 26 weeks × 52 jurisdictions that is ~4,000 distinct as-of feature vectors, each requiring a separate vintage query. This is the single largest engineering cost of any NN pilot and it is usually skipped.
- *Scoring:* against the finalised target, as FluSight does.
- The Delphi `epiprocess` / `epipredict` tooling formalises this via `epix_slide()`, and its documentation states the conclusion bluntly: "Good performance of a version un-faithful model is a mirage; it is only achievable if the training data has no revisions." ([backtesting vignette](https://github.com/cmu-delphi/epipredict/blob/main/vignettes/backtesting.Rmd); underlying result in [Reinhart et al., *PNAS* 118:e2111452118, 2021](https://doi.org/10.1073/pnas.2111452118).)

**One asymmetry worth noting.** FluBNF's vintage archive covers the target stream. Several channels the user listed — NHSN age strata, NHSN occupancy/ICU, NWSS wastewater — have **no public vintage archive at all**, per the memo's audit. A NN consuming those channels cannot be honestly backtested today at any price.

### 5.3 Quantile calibration

**How these models produce 23 quantiles.** Four mechanisms, with different reliability:

1. **Pinball loss, one fit per quantile level** (Flusion's GBQR, CMU-TimeSeries, TFT). The most reliable, and the only one with a FluSight track record. Requires post-hoc sorting to prevent quantile crossing — CMU-TimeSeries applies "nonnegativity and quantile sorting constraints… post hoc."
2. **Parametric output head** (DeepAR): the network emits distribution parameters, quantiles come from the parametric family. Calibration is then hostage to the family choice.
3. **Sampling / MC dropout / deep ensembles**: computationally heavy and, per EpiFNP's own framing, "methods like deep ensembling can be computationally expensive" while Bayesian NNs suffer because "it is difficult to specify proper priors."
4. **Post-hoc conformal wrapping**: distribution-free coverage guarantees, but marginal rather than conditional — and conditional coverage during the turn is exactly what FluBNF needs.

**Are they well-calibrated in practice? Mostly no, and typically overconfident.** The FluSight evidence:
- VTSanghani-ExogModel (pure AI/ML): 30% / 61% against nominal 50% / 95%.
- GT-FluFNP, a model *explicitly designed for calibration*: 39% / 69% in 2021-22, improving to 56% / 75% in 2022-23 — still materially under-covering at the 95% level.
- MIGHTE-Nsemble (LightGBM + ARIMA): 53% / 82% — the best-calibrated ML entrant, and it is trees.
- Flusion: 55.8% / 96.3% — *under*confident, the same direction as FluBNF.

*(Reasoning.)* The pattern across these numbers is that gradient-boosted pinball-loss models land close to nominal, while neural quantile models under-cover. That is what you would expect from a high-capacity model fit to few effective observations: it fits the conditional median reasonably and dramatically underestimates predictive variance, because it has not seen enough distinct season shapes to know how wrong it can be.

### 5.4 Ensemble interaction — the arithmetic that settles it

FluBNF averages quantiles at equal weights. This has a specific and useful mathematical consequence.

**Vincentisation identity.** For quantile averaging, the α-quantile of the combination is the arithmetic mean of the members' α-quantiles. Therefore the ensemble's central interval width at any level is *exactly* the arithmetic mean of the members' interval widths at that level.

Three consequences follow immediately, and they are facts rather than opinions:

1. **A member wider than the current ensemble makes the ensemble wider.** No amount of median accuracy compensates. Since FluBNF's stated defect is excess width, and Flusion — the best documented model of this family on this target — was itself too wide, this is a direct strike against the whole approach.
2. **The third member gets weight 1/3, taking 1/6 from each incumbent.** With the oracle over the two current members at 0.737 pooled (per the brief), the achievable movement from any third member is bounded, and the ~5% noise floor eats most of it. This mirrors CDC's own finding that the 2024-25 top ten fell within 0.04 relWIS of each other.
3. **This yields a free pre-screen that costs no fitting.** Before running a single retrospective grid, compute the candidate member's mean 50% and 95% interval widths on the historical cells and compare to the current 2-member ensemble's. *If the candidate is wider, it cannot help with the stated defect and should be rejected before any WIS is computed.* This is the width analogue of the memo's Law 7 echo test, and it is a similarly cheap way to kill a bad candidate in an afternoon.

There is one genuine upside worth stating fairly: quantile averaging of members with *differently shaped errors* is where ensembles earn their keep, and this is the argument the memo's §4.7 makes for a statistical member. A neural member would certainly have differently shaped errors. The question is whether those errors are differently shaped *and* smaller, and §2 says no one has shown that.

---

## 6. Recommendation

### 6.1 Ranked shortlist

**Rank 0 — Build no neural member. Recommended.**
The evidence base does not support it. The four specific reasons, in order: no neural network has topped FluSight in any hospital-admissions season; the one pure AI/ML entrant was the worst-calibrated model in the published table; FluBNF's defect is width and this family does not fix width; and the vintage-honest training infrastructure required is the most expensive part of the build with the highest chance of producing a mirage. Close the `einn` stub with a pointer to this document.

**Rank 1 — If a member from this literature must be built: GBQR ("Flusion-lite").**
LightGBM quantile regression, one fit per quantile level, bagged, trained **jointly across all jurisdictions** and on **NHSN + ILI+ (or NREVSS-derived) rows as extra training examples**, predicting the *change* in a transformed signal rather than its level. Rationale: it is the only ML family with a documented FluSight win; it emits 23 quantiles natively; it lands near nominal coverage in the two hub instances we can observe; it needs no fitted ensemble weights; and the ablation tells us exactly which two design choices carry the effect (joint-across-locations, joint-across-signals), so there is little to tune and therefore little to overfit.

I still rank this **below the memo's candidate 4.1** (two-strain gated by typed-specimen sufficiency), because 4.1 reuses a member that already passed the turn gate twice, costs weeks rather than months, and is fully vintage-honest today. Rank 1 here is best read as a *replacement for the memo's §4.7 statistical member* — a better-evidenced version of the same idea — to be built only under the memo's stated condition: if candidates 1–3 all return nulls.

**Rank 2 — Zero-shot foundation model probe (TimesFM or TabPFN-TS), as a two-day measurement, not a member.**
The only NN-adjacent option that clears the data-volume bar, because it does not train. Its unique attraction is that with no training step there is no training-data leakage surface. Worth two days to measure, not worth a program. Would be the first FluSight-grid evaluation of these models that I can find, which is itself a reason to be sceptical of a good result.

**Rank 3 — TinyLSTM with a pinball-loss head.**
Only if Rank 1 succeeds and the team wants a differently-shaped-error member. Documented as the best pure-hospitalisation neural architecture at exactly three seasons of data — which is a statement about how low the ceiling is, not a recommendation.

**Rank 4 — EINN, TFT, DeepAR, N-BEATS, GNN, neural ODE. Do not build.**
Infeasible at this data volume, no quantiles, or both. EINN specifically fails on the quantile blocker before data volume is even reached.

**Explicitly rejected — a multi-input NN over the channel list in the brief.**
This is the user's stated instinct and it is the weakest option on the list. It combines the highest parameter count, the largest leakage surface, the channels with no vintage archive, and the only architecture family with zero wins on this target. It is also *not* what Flusion did, despite Flusion being the model usually cited to justify it.

### 6.2 A minimal honest pilot for Rank 1

Written in the memo's idiom so it can be pre-registered alongside the other candidates.

**Free triage first — three measurements before any fitting.** All are cheap, and any one of them failing should stop the program.

1. **Width screen (§5.4).** Fit GBQR on final data, ignoring vintages entirely, for one season. Compute mean 50% and 95% interval widths and compare to the production 2-member ensemble on identical cells. *If GBQR is wider, stop.* This is a one-day check that costs nothing and directly tests the stated defect. Flusion's published coverage (55.8 / 96.3) predicts it may well be wider, which is why this goes first.
2. **Leakage-delta screen.** Score the same final-data GBQR twice: once on all cells, once restricted to cells where the last observation was ultimately revised by <1%. If the two relWIS numbers differ materially, the honest number is the second one, and the team should assume the full vintage-true number will be worse still. This is Bracher & Funk's Table 1 applied prospectively to FluBNF's own candidate.
3. **Auxiliary-row availability audit.** Confirm how many vintage-true ILI+/NREVSS rows can actually be reconstructed as of each historical reference date. Flusion's entire margin came from these rows; if they cannot be reconstructed vintage-true, the member reduces to GBQR-only-NHSN, which scored 0.857 — worse than the FluSight ensemble and worse than several mechanistic models.

**Then, only if all three pass:**

- **Arms.** D0: production 2-member 50/50. D1: 3-member equal weights with GBQR. D2: GBQR alone, as a member-quality floor.
- **Vintage discipline.** Mandatory and non-negotiable. Every training row's features as-of that row's reference date; scoring against finalised target. Budget this as the majority of the build.
- **Selection surface.** Fixed a priori: quantile levels = the 23 required; bagging 100 fits at 70% of seasons; features restricted to season week, population, transformed recent observations, trend, curvature, horizon, Christmas proximity — the top features Flusion reported. **No hyperparameter search.** Any tuning re-opens Law 1 through the back door.
- **Gate 1 (width).** D1's mean interval widths ≤ D0's on identical cells. Fails ⇒ stop.
- **Gate 2 (turn).** D1 beats production on Feb-2024 and Jan-2025 as-of months, paired seeds, identical cells.
- **Gate 3 (seat).** D1 beats D0 on identical full-grid cells, all seasons pooled, by more than the 5% noise floor.
- **Floor.** Member relWIS < 1.1 in every season.
- **Report regardless of outcome:** the leakage delta from triage 2, per-horizon breakdown, and empirical 50%/95% coverage of the member against nominal.

### 6.3 What would falsify it

Pre-register these so the result cannot be argued into a success afterwards:

- **GBQR's interval widths exceed the current ensemble's.** Kills it outright — it cannot address the stated defect. *This is the single most likely failure, given Flusion's published underconfidence.*
- **The vintage-true relWIS is more than ~0.03 worse than the final-data relWIS.** Indicates the member's apparent skill was revision leakage; report the vintage-true number and stop.
- **Pooled full-grid movement under 5%.** Below the noise floor; a null, and the member does not earn a seat.
- **Gain concentrated at horizon 0–1 only.** A real but small nowcasting result. Report it as such; do not seat a member on it.
- **The member helps on the descent but not the turn.** The open problem is the turn. A member that only improves easy phases is not the member being sought.
- **Vintage-true auxiliary rows cannot be reconstructed**, reducing the member to GBQR-only-NHSN. That variant scored 0.857 in Flusion's own ablation, worse than several existing FluSight models — not worth a seat.

---

## 7. Multi-input specifically: which channels are documented to help

The user's list, assessed against what published NN/ML forecasting work actually shows. "Echo" is used in the team's sense: correlates concurrently with admissions but adds nothing after conditioning on admissions history.

| Channel | Documented predictive value in published forecasting work | Vintage-capable? | Verdict |
|---|---|---|---|
| **NHSN admissions** (target) | The dominant feature. Flusion's top features are season week, population, most recent observation, horizon, Christmas proximity | Yes (Delphi `nhsn`, FluSight target archive) | Already used |
| **ILINet / ILI+** | **Strongest documented auxiliary.** Flusion 0.857 → 0.625 when added as training rows; CMU-TimeSeries whitens and appends it; ERA supplied ~20 years of it. **But used as extra training rows, not contemporaneous features** | Yes (Delphi `fluview`) | **The one clearly worth having** — as history, not as a predictor |
| **NREVSS typed A/B** | Component of ILI+; already in FluBNF via `flubnf/nrevss.py` with verified lag-1 vintages | Yes, verified | Already available; funds memo candidate 4.1 |
| **FluSurv-NET** | Flusion's second auxiliary signal, same transfer-learning role | **No** as a real-time channel — memo measured 36–52 week publication lags. Fine as fixed climatology | History only |
| **NHSN age strata** | No published NN forecasting evaluation I could find. Memo measures a genuine lead (+0.32 partial correlation) | **No public vintage archive**; one Internet Archive snapshot exists | Promising mechanistically (memo 4.2); **unusable in a NN today** for lack of vintages |
| **NHSN occupancy / ICU** | No published NN value found | No | **Documented echo.** Memo measured partial correlation −0.03 against next-week growth despite raw −0.75. Do not feed to anything |
| **Wastewater (NWSS)** | No published evidence of NN forecasting gains at the FluSight target | **No** — all rows share one `date_updated`; as-of reconstruction impossible | **Net lead ≈ 0** at the submission deadline (memo Law 5). Archive, do not build |
| **ED visits (NSSP)** | Now a FluSight *target* in its own right for 2025-26, and a vintage archive exists from 2025-11-15 | Partially, and only recently | **The team's documented echo case.** Its promotion to a forecast target does not make it a predictor of admissions |
| **Weather / humidity** | Long-standing mechanistic literature on absolute humidity and transmission; I found **no** evidence of WIS gains from adding it as a NN feature on this target | Yes (no revisions) | Not supported by forecasting evidence |
| **Google / search trends** | The **most cautionary channel in this field.** [Lazer et al., *Science* 2014](https://doi.org/10.1126/science.1248506): GFT overfit 50M search terms to 1,152 data points, missed the 2009 H1N1 pandemic, and "missed high for 100 out of 108 weeks starting with August 2011." Failure causes were overfitting and *algorithm dynamics* — the data-generating process changes underneath you for commercial reasons | Effectively no; the series is retroactively redefined | **Avoid.** Note this is the channel EINN's influenza experiment used |

**The synthesis the user should take from this table.** The channel that demonstrably improves forecasts on this exact target is ILINet/ILI+, and the mechanism by which it helps is *lengthening the training history*, not *leading the target*. Every other channel on the list is either an echo, un-vintageable, published too late, or carries a documented history of spurious success. This is the same conclusion the member-search memo reached by direct measurement, arrived at independently from the forecasting literature — which is mildly reassuring about both.

---

## 8. What I could not verify

Listed without softening.

**Numbers I could not obtain.**
- **Model-by-model relWIS tables for FluSight 2023-24 and 2024-25.** The CDC evaluation pages render Table 1 and Table 2 dynamically; I retrieved only the surrounding narrative. So "the ensemble beat 27 of 28" (2023-24) and "the ensemble outperformed all submitted models" (2024-25) are CDC's own prose, which I trust, but **I do not have per-model relWIS or coverage for those two seasons and therefore cannot say where any specific neural model ranked in them.** This is a real gap: two of the four seasons the brief asked about are covered only at narrative level. Anyone wanting those rows should pull them from the [FluSight hub repository](https://github.com/cdcepi/FluSight-forecast-hub) directly.
- **What `UM_DeepOutbreak` scored in 2024-25.** It appears in the CDC report with an asterisk: "Forecasts from the UM_DeepOutbreak model were generated based on an incorrect data field for part of the season." I could not determine its relWIS, and given the data error its result would be uninterpretable anyway. This is the most likely candidate for a genuinely deep-learning FluSight entrant in that season and I cannot report on it.
- **Whether `GT-FluFNP` is in fact EpiFNP.** Inferred from the name, the lab and the timing. CDC's keyword classifier tagged it STAT, not AI/ML, which is either a classifier artefact or evidence that it is not what I think it is. If this inference is wrong, then the best neural result I report in §2.1 is not neural, and the case against neural members is *stronger*, not weaker.
- **PSI-PROF_beta's method.** Top individual model in 2024-25; I did not verify whether it has ML components.

**Claims I am relying on that are not peer-reviewed.** "A Decade of CDC FluSight" (medRxiv, June 2026), Bracher & Funk (arXiv 2608.05883), Martinson et al. (arXiv 2605.16238), Jafari et al. (arXiv 2606.19560), and Wang/Li/Perra (medRxiv 2026) are all preprints. The Bracher & Funk re-analysis is the most consequential of these for my recommendation; it is a short note, its replication code is public ([jbracher/era-replication](https://github.com/jbracher/era-replication)), and I did not run it.

**Comparability problems I did not resolve.**
- The Jafari benchmark that I lean on for the "three seasons ⇒ TinyLSTM" conclusion reports **mean MSE on normalised HHS-region series**, not WIS on the 50-state grid. Its model ordering may not survive translation to quantile scoring, and HHS regions are smoother than states. This is the weakest load-bearing citation in the briefing and it should be treated as indicative.
- Relative WIS is **not comparable across the sources I quote**. Mathis et al. (2021-22, 2022-23) use untransformed counts with a pairwise-ratio normalisation; the CDC 2023-24 and 2024-25 reports use **log-transformed** counts with geometric means; Flusion's rMWIS is a mean-WIS ratio on state-level horizons 0–3. I have not attempted to reconcile them and **no number in this briefing should be compared across seasons or across sources.**

**Things I did not attempt.**
- I did not verify any of FluBNF's internal figures (the 0.737 oracle, the 0.953/0.968 turn-gate results, the 5% noise floor). All are taken from the brief and the member-search memo as given.
- I did not run any code, fit any model, or compute any number. Every quantity here is quoted from a cited source or is arithmetic on quoted quantities.
- I did not search non-English literature, and I did not systematically cover European (RespiCast/ECDC) or UK hub evaluations beyond what surfaced incidentally.
- **I did not find any published head-to-head of mechanistic vs. deep-learning vs. hybrid on FluSight with matched vintage discipline.** The brief asked for this specifically. As far as I can tell it does not exist. The closest substitutes are the Decade paper's category-level test (which found no significant differences in the hospital-admissions era) and Flusion's ablation (which is within-family). **The absence of this comparison is itself the most important thing I have to report: the confident claims in this space are not backed by the study that would settle them.**

---

## Appendix: primary sources

**Hub evaluations**
- Mathis et al. Evaluation of FluSight influenza forecasting in the 2021–22 and 2022–23 seasons. *Nat Commun* 15:6289 (2024). https://doi.org/10.1038/s41467-024-50601-9
- CDC. FluSight 2023-2024 Evaluation. https://www.cdc.gov/flu-forecasting/evaluation/2023-2024-report.html
- CDC. FluSight 2024-2025 Evaluation. https://www.cdc.gov/flu-forecasting/evaluation/2024-2025-report.html
- A Decade of CDC FluSight Influenza Forecasting. medRxiv 2026 (preprint). https://www.medrxiv.org/content/10.64898/2026.06.05.26354941v1.full-text
- Cramer et al. Evaluation of individual and ensemble probabilistic forecasts of COVID-19 mortality in the United States. *PNAS* 119:e2113561119 (2022). https://doi.org/10.1073/pnas.2113561119
- FluSight Forecast Hub. https://github.com/cdcepi/FluSight-forecast-hub

**Winning and near-winning models**
- Ray et al. Flusion: Integrating multiple data sources for accurate influenza predictions. *Epidemics* 50:100810 (2025). https://doi.org/10.1016/j.epidem.2024.100810 · code https://github.com/reichlab/flusion
- Martinson et al. Prospective multi-pathogen disease forecasting using autonomous LLM-guided tree search. arXiv:2605.16238 (2026, preprint). https://arxiv.org/abs/2605.16238

**Vintage-honesty and leakage**
- Bracher & Funk. Information leakage from data revisions in retrospective forecasts. arXiv:2608.05883 (2026, preprint). https://arxiv.org/html/2608.05883
- Aygün et al. An AI system to help scientists write expert-level empirical software. *Nature* 654:909–916 (2026). https://doi.org/10.1038/s41586-026-10658-6
- Reinhart et al. An open repository of real-time COVID-19 indicators. *PNAS* 118:e2111452118 (2021). https://doi.org/10.1073/pnas.2111452118
- Delphi `epipredict` backtesting vignette. https://github.com/cmu-delphi/epipredict/blob/main/vignettes/backtesting.Rmd
- Delphi-RF: Real-time forecasting of data revisions in epidemic surveillance streams. *PLOS Comput Biol* (2025). https://doi.org/10.1371/journal.pcbi.1013709

**Neural architectures and epidemic NN work**
- Rodríguez et al. EINNs: Epidemiologically-Informed Neural Networks. *AAAI* 37(12):14453–14460 (2023). https://doi.org/10.1609/aaai.v37i12.26690
- Kamarthi et al. When in Doubt: Neural Non-Parametric Uncertainty Quantification for Epidemic Forecasting (EpiFNP). *NeurIPS* (2021). https://arxiv.org/abs/2106.03904
- Lim et al. Temporal Fusion Transformers for interpretable multi-horizon time series forecasting. *IJF* 37(4):1748–1764 (2021). https://arxiv.org/abs/1912.09363
- Salinas et al. DeepAR. https://arxiv.org/abs/1704.04110

**Foundation models and benchmarks**
- Foundation models for time series forecasting and policy evaluation in infectious disease epidemics. *Epidemics* (2026). https://doi.org/10.1016/j.epidem.2026.100916 · preprint https://doi.org/10.1101/2025.02.24.25322795
- Jafari et al. Understanding Key Features of Time Series Foundation Models from Epidemic Forecasting. arXiv:2606.19560 (preprint). https://arxiv.org/abs/2606.19560 · code https://github.com/alireza-jafari/Epidemic-Times-Series-Foundation-Models-Benchmark
- Wang, Li & Perra. From naive to foundation: benchmarking models for epidemic forecasting. medRxiv 2026 (preprint). https://www.medrxiv.org/content/10.64898/2026.05.11.26352889v1.full-text

**Cautionary**
- Lazer, Kennedy, King & Vespignani. The Parable of Google Flu: Traps in Big Data Analysis. *Science* 343:1203–1205 (2014). https://doi.org/10.1126/science.1248506
