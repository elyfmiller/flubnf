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
