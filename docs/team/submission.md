# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-09-30: cdcepi/FluSight-forecast-hub#3713 (opened by Ely) updates
  both cards on the hub, from branch `NAU_PyBNF-metadata-update` of
  elyfmiller/FluSight-forecast-hub (cdb1a878). GitHub's test merge changes
  only the two cards, byte-identical to FluBNF's `model-metadata/` on
  `dev`, and hubValidations passes both (6 of 6). Waiting on CDC to merge;
  then that branch can go. The fork's other branches are deleted.
- 2026-09-30: the Oracle SIHRS card names the Liu-West filter (b41fc92).
- 2026-09-30: both model cards designated for `wk inc flu hosp` only, and
  the vendored hub metadata schema brought up to date (0e6e3cc). Both
  commits are in elyfmiller/flubnf#26 until it merges.
- 2026-09-30: the weekly file passes CDC's own validator
  (`scripts/validate_submission.R`, 28 of 28 checks) for a Groundhog
  real-time run (as-of 2026-09-26) and a replay (as-of 2026-01-10); the
  model lane's Oracle SIHRS replay file passes too (model.md: GREEN).
- 2026-09-30: the hub holds the cards of cdcepi/FluSight-forecast-hub#3705
  (merged 2026-09-24), one version behind ours (Groundhog 1.0, Oracle
  SIHRS 1.1), until #3713 merges.

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

- Model (answering your notes of 2026-09-30): noted: 2026-10-07 runs both
  models on `main` with the Data issues box's preselected choices and
  `run.drop_same_day` off; short newest weeks explain the Oracle SIHRS's
  coverage; the wide early-season Groundhog tails are expected. Thanks for
  the card wording: it goes to the hub with Ely's pull request.
- Model: thanks for the GREEN on the Oracle SIHRS file; request closed.
- App (answering your request of 2026-09-30): done: "Liu-West" with a
  hyphen in this file too.
- App: `app/tests/test_model_metadata.py` now handles `oneOf` (0e6e3cc).
  If CDC changes its metadata schema again, the test fails wherever the
  hub clone is current: re-vendor the schema and update `SCHEMA_SHA256`.

## Open
