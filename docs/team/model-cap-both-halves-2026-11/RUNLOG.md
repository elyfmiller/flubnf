# Run log: the tail cap on both halves, Groundhog half

Model lane, Ely's Windows PC. Times UTC.

- 2026-11-10, before the freeze: `both.py` written. As a code check it ran
  `week_arms` and `check_week` on three 2023-24 weeks (2023-10-14,
  2023-11-18, 2024-01-06). That read no truth and scored nothing: 25 arms
  per week, no defect.
- 2026-11-11 01:31: `prereg.txt` frozen, sha256 67262c94...a0d, and made
  read-only. Copies are in the research folder.
- 02:26 to 02:30: the repository move (App). This clone was reset to the
  new `dev` 9b3e658b before any commit.
- 02:33:12: commit d3996ecd (the prereg, its sha256 file, `both.py`, the
  model.md entry), pushed to `dev` at once. The committed blob hashes to
  67262c94...a0d, byte for byte.
- 02:34:48 to 02:38: `both.py --season` for 2023-24, 2024-25 and 2025-26
  on code d3996ecd, hub 3a83d410 (32, 30 and 31 weeks; no defect; 3.9
  minutes in all). Each run first checks the stored forecasts' sha256
  against the prereg; all three match.
- The first `--report` stopped at its first table. pandas reads `.asof` on
  a DataFrame as its method `DataFrame.asof`, so the list of EARLY weeks
  failed. Before stopping it had printed only the cell count (17,116 per
  arm). The two lines now read the column as `["asof"]`, and the report
  then ran in full ([report.txt](report.txt)). No rule, arm, subset or
  threshold changed.

Amendment 1 (the lower half balanced in admissions, BN):
- 2026-11-11 05:05:59: `AMENDMENT1.txt` frozen (sha256 c8db37b6...), after
  Part 1's results and Ely's reading of them. It went out in commit
  9c63e563, pushed at once; the committed blob matches the hash.
- 05:07:04 to 05:07:50: `amend1.py --season` for the three seasons (0
  defects; 79 horizon-blocks left alone for a 2.5% quantile of 0), then
  `--report` ([report_amend1.txt](report_amend1.txt)). `amend1.py` was
  written after the freeze and before its first score. It reads Part 1's
  arms from the same results folder.

Amendment 2 (the level on the Oracle's own October rounds):
- 2026-11-11, before the freeze: `amend2.py` written. This lane's hub
  clone moved from 3a83d410 (Part 1's) to a73013aa (cdcepi main of
  2026-11-09: the October rounds, their vintages, truth through 10-31).
  `amend2.py --check` ran on the rounds' rows and vintages only, reading
  no truth: 0 defects. Its counts are in AMENDMENT2.txt.
- 2026-11-11 07:06:50: `AMENDMENT2.txt` frozen (sha256 f6ea323a...),
  made read-only, and pushed with `amend2.py` before its first score.
- The first `amend2.py --score` stopped before printing anything, on the
  same pandas slip as Part 1's first report (`.asof` read as the
  DataFrame's method). The two lines now read the column as `["asof"]`.
  No rule, arm, measure or threshold changed.
- The second ran in full but printed every coverage as NaN: score_week
  labels the bands "50" and "95" as strings, and the report compared them
  with numbers (both.py had read them back from csv). P3 printed "fails"
  on NaN. The coverage line now compares the labels as strings, and the
  report was run again ([report_amend2.txt](report_amend2.txt)). WIS, the
  bootstrap and the rule were the same in both runs; the coverage was
  first seen in the third.
- Afterwards this lane's hub clone went back to 3a83d410, Part 1's.
- The App lane reproduced it on Ely's laptop, from a sparse clone of the
  hub at a73013aa. `--check` and `--score` gave a report byte-identical to
  report_amend2.txt.
- Read after the scores (descriptive, this lane's scratchpad scripts,
  checking App's review):
  - Part 1's S10-RX against S10-R3 by season and as-of month, with the
    95% coverage of S10-R3.
  - Truth above the 97.5% quantile by member and round.
  - The submitted round 10-31 at h0 (hub a73013aa for these, then back to
    3a83d410).
  - The 10-31 vintage's last week over the three-week mean.
  The figures are in model.md, Now, 2026-11-11 07:10 UTC.

Read after the scores (descriptive, not in the rule):
- LN against S gives the same difference at every cap and level (-0.0003
  pooled). WIS is a sum over the quantile levels, so a change below the
  median scores apart from the upper half; the same holds for the share
  of truths below the 2.5% quantile. So LN against S measures the lower
  narrowing alone.
- Sep-Oct is 2023-24's four October as-of weeks (772 cells), the only
  October weeks in the three seasons. There the truth fell below the
  forecast often even with no cap (8.2% below the 2.5% quantile), and
  every lower-half rule makes that worse (M10-R3 27%). The mirror's
  2023-24 loss against S10-R3 comes from the weeks of 2023-10-07 to
  2023-11-11, each costing 0.0007 to 0.0013 of the season's baseline.
