# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-09-30: the hub update of both cards is ready on Ely's fork, branch
  `NAU_PyBNF-metadata-update` of elyfmiller/FluSight-forecast-hub
  (c736656, on top of the merged `NAU_PyBNF-metadata`). The cards are
  byte-identical to FluBNF's `model-metadata/` on `dev`, and the branch
  test-merges cleanly into cdcepi `main`, changing only those two files.
  Ely opens the pull request.
- 2026-09-30: the Oracle SIHRS card names the Liu–West filter (b41fc92).
- 2026-09-30: both model cards designated for `wk inc flu hosp` only, and
  the vendored hub metadata schema brought up to date (0e6e3cc). Both
  commits are in elyfmiller/flubnf#26 until it merges.
- 2026-09-30: the weekly file passes CDC's own validator
  (`scripts/validate_submission.R`, 28 of 28 checks) for a Groundhog
  real-time run (as-of 2026-09-26) and a replay (as-of 2026-01-10). No
  Oracle SIHRS file checked yet (no engine in the cloud): run the script
  on the first one.
- 2026-09-30: the hub holds the cards of cdcepi/FluSight-forecast-hub#3705
  (merged 2026-09-24), one version behind ours (Groundhog 1.0, Oracle
  SIHRS 1.1), until Ely's pull request merges.

## Decided

- 2026-09-30 (Ely): the 2026-27 scope is `wk inc flu hosp` only:
  quantiles, horizons 0 to 3, all 53 locations. No ED-visit, peak,
  rate-change or horizon -1 rows; the knobs `output.horizon_minus1` and
  `output.rate_change_pmf` stay off.
- 2026-09-30 (Ely): both models are designated for that target alone
  (`designated_targets` in both cards).
- 2026-09-30: the hub's cards are byte copies of FluBNF's
  `model-metadata/`: change a card there first (its tests check it
  against the hub schema), then the submission lane copies it to the fork.

## For other lanes

- Model: please check the Oracle SIHRS card's new wording (b41fc92):
  "fitted weekly by the Liu-West filter" in `methods`, "the Liu-West
  filter (a particle filter, in a PyBNF fork on bngsim)" in
  `methods_long`, and "from a past season" for "from an earlier season"
  (`methods` is capped at 200 characters). The card must stay ASCII,
  hence the hyphen. Tell Ely before the hub pull request is opened if
  anything should change.
- App: FLUSIGHT-2026-27.md still lists "the Oracle SIHRS card still says
  'particle filter'" as open; FluBNF's card is fixed (b41fc92), and the
  hub's follows with Ely's pull request.
- App: `app/tests/test_model_metadata.py` now handles `oneOf` (0e6e3cc).
  If CDC changes its metadata schema again, the test fails wherever the
  hub clone is current: re-vendor the schema and update `SCHEMA_SHA256`.
- Model: early-season Groundhog tails are wide (as-of 2026-09-26, US
  three weeks ahead: median 4,672, 0.99 quantile 90,434, from 2,515). No
  hub rule is near; no action asked.

## Open

- Ely opens the hub pull request from `NAU_PyBNF-metadata-update`. Not
  needed for 2026-10-07: a designated model already counts for every
  target it submits.
