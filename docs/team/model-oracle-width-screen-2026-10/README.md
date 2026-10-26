# The Oracle SIHRS width screen: the records

These are the records behind the Model lane's entries of 2026-10-22 to
2026-10-25 in [model.md](../model.md) (the Oracle SIHRS agent's, lab
Mac). They are here at Ely's word of 2026-10-25 ("make sure your results
are visible to the Team agent through the repo"), so a reviewer can check
every number in those entries without the lab Mac. Research files, not
runtime: nothing in the console imports them, and no test reads them.

The screen: 84 as-of weeks of 2023-24 to 2025-26, 17,466 scored state cells
per rule, settled truth, FluSight's cell rule and baseline join. The
replayed arms are C0, REG, R20, R22, HP and HS. The post hoc arms are the
caps on C0's stored samples, the trajectory exclusion X and the historical
ceiling H.

## prereg/: the rules, written before the scores

| File | What | Frozen |
|---|---|---|
| PREREG.md | the screen: arms, scoring, checks A to C, the reading rule (section 6) | 2026-10-22 04:38 UTC |
| AMENDMENT_REG.md | the registered member as a step table | 2026-10-22 04:56 UTC |
| AMENDMENT1.md | the past-season boxes of HP and HS (from boxes.json, hs_table.json) | 2026-10-23 00:32 UTC |
| AMENDMENT2_EXCL.md | the trajectory-exclusion arm X | 2026-10-24 07:03 UTC |
| AMENDMENT3_HIST.md | the historical ceiling H and its pass rule for 2026-10-28 | 2026-10-25 23:41 UTC |

The texts are byte-identical to the lab Mac's frozen files. To verify
them, from this folder:

    shasum -a 256 -c SHA256SUMS

Each `*.sha256` file is the lab Mac's own record (PREREG's and
AMENDMENT3's carry the freeze time; the others' times above are the files'
last write, after which they were made read-only).
Two notes on the frozen texts:
- PREREG.md and AMENDMENT1.md say "posterior median(s)" for the season-end
  fitted parameters, in the house words the medians of the Liu-West
  filter's fitted parameters. They are left as written so the hashes
  verify.
- AMENDMENT2_EXCL.md calls its September to November subset "24 weeks, as
  in the C0 reading", but report_excl.py read the 14 as-of weeks dated
  September to November. The C0 reading's early subset is the first 8
  scoreable weeks of each season, 24 weeks. AMENDMENT3_HIST.md records
  this correction, and reports/report_X_early24.txt re-reads X on the 24
  weeks: the conclusion is unchanged.

## scripts/: how the cells were made and read

The scripts run on the lab Mac from the screen directory
(`research/oracle-width-screen` in the lab's FluBNF-local tree), with
`env.sh` sourced. In these copies the lab's home directory is written `~`.
The code they score with is two detached worktrees of the console:
- `wt`, at 744e654, for the replays and the cap arms;
- `wt-hist`, at main a99d53d, which carries the knob output.tail_hist.

| Script | Does | Writes |
|---|---|---|
| env.sh | the screen's worktree, hub, engine and the live knobs | |
| run_arm.py, launch_arm.sh, chain.sh | the replays, one arm a season, through `flubnf.cli_retro` | `arms/<arm>/<season>/` |
| score_arm.py | every stored week scored under every k and output rule; checks A to C | `arms/<arm>.cells.pkl` |
| build_boxes.py | the HP and HS boxes from the season-end fits (AMENDMENT1) | boxes.json, hs_table.json |
| report.py | the reading of an arm, the arm against C0 (PREREG section 6), and the step table | report_C0, report_R20, report_R22, report_HP, report_HS, steps_REG_C0 |
| c0_early.py | C0's caps on the 24 early weeks | report_C0_early |
| hp_extra.py, hp_where.py | HP's exact held-out values, fixed settings, months and states | report_HP_extra, report_HS_extra |
| exclude_arm.py, report_excl.py | the trajectory exclusion X (AMENDMENT2), checks A' to C' | report_X |
| x_early24.py | X on the 24 early weeks | report_X_early24 |
| hist_arm.py, report_hist.py | the historical ceiling H (AMENDMENT3), checks A3 to D3, the predictions and the pass rule | report_H |
| h_extra.py, h_argmax.py | H's exact coverage, the October mechanism, the cells that set the maxima | report_H_extra, report_H_argmax |
| export_week_sums.py | the week-level sums in data/ | data/ |

## reports/: the full outputs

Each `reports/*.txt` is exactly what its script printed. There is one
exception: report_HP_extra.txt kept the traceback of a failed first run of
hp_where.py (a pandas attribute error), and in this copy a one-line note
stands in its place.

## data/: enough to recompute every pooled number

The per-cell tables (arms/*.cells.pkl, 1.3 million rows for C0) and the
stored samples stay on the lab Mac and are available on request. What is
here:

- `week_sums_H.csv`, `week_sums_X.csv`: one row per (season, asof,
  horizon, k, rule [, variant]) for the post hoc arms.
- `week_sums_<arm>.csv.gz` for the replayed arms C0, REG, R20, R22, HP and
  HS: one row per (season, asof, k, rule), the four horizons summed (their
  by-horizon numbers are in the reports).
- Each row: `n` cells; the sums `wis`, `base_wis`, `log_wis`,
  `base_log_wis`; the counts covered at 50, 80 and 95%; and `h3_cells` and
  `h3_over30`, the h3 cells with the 97.5% quantile over 30x the recent
  level.
- `hist_ratios.csv`: the ceiling's ratio and pool size per week, source
  (v the week's vintage, f the settled truth), level and horizon.
- `hist_blocks_touched.csv`: per week and horizon, the blocks the ceiling
  changed (any level, the 97.5% itself, collapsed to the median), and the
  blocks where the pairing's rows differ from shrink 15x's.

How the numbers are computed from these sums:
- Pooled relWIS is `sum(wis) / sum(base_wis)`, and on the log scale
  `sum(log_wis) / sum(base_log_wis)`.
- Coverage is `sum(cov95) / sum(n)`.
- The week-cluster bootstrap resamples the as-of weeks, 2,000 times with
  numpy's default_rng(20261022), as in report.py's boot_diff. It uses the
  week totals of two rules: the arm's wis and base_wis, and the
  reference's wis.

For example, the historical ceiling's pairing minus shrink 15x:

    import numpy as np, pandas as pd
    h = pd.read_csv("data/week_sums_H.csv")
    wk = lambda r: h[h.rule == r].groupby(["season", "asof"])[["wis", "base_wis"]].sum()
    a, b = wk("hist max+shrink 15x"), wk("shrink 15x")
    M = np.c_[a.wis, b.wis, a.base_wis]
    st = lambda M: (M[:, 0].sum() - M[:, 1].sum()) / M[:, 2].sum()
    rng = np.random.default_rng(20261022)
    bs = [st(M[rng.integers(0, len(M), len(M))]) for _ in range(2000)]
    print(st(M), np.percentile(bs, [2.5, 97.5]))   # -0.0060 [-0.0140, -0.0004]
