# Submission lane notes

The weekly FluSight run: data checks, validation, the hub pull requests
and CDC's rules. The season's facts are in
[FLUSIGHT-2026-27.md](../FLUSIGHT-2026-27.md).

## Now

- 2026-09-30: both model cards designated for `wk inc flu hosp` only, and
  the vendored hub metadata schema brought up to date (0e6e3cc on `dev`,
  so in elyfmiller/flubnf#26 until it merges). The hub's copies are not
  updated yet (Open).
- 2026-09-30: the weekly file passes CDC's own validator
  (`scripts/validate_submission.R`, 28 of 28 checks) for a Groundhog
  real-time run (as-of 2026-09-26) and a replay (as-of 2026-01-10). No
  Oracle SIHRS file checked yet (no engine in the cloud): run the script
  on the first one.
- 2026-09-30: both cards are on the hub (cdcepi/FluSight-forecast-hub#3705,
  merged 2026-09-24), one version behind ours (Groundhog 1.0, Oracle
  SIHRS 1.1).

## Decided

- 2026-09-30 (Ely): the 2026-27 scope is `wk inc flu hosp` only:
  quantiles, horizons 0 to 3, all 53 locations. No ED-visit, peak,
  rate-change or horizon -1 rows; the knobs `output.horizon_minus1` and
  `output.rate_change_pmf` stay off.
- 2026-09-30 (Ely): both models are designated for that target alone
  (`designated_targets` in both cards).

## For other lanes

- Engine (answering your request of 2026-09-30): the weekly run needs the
  lab Mac on Wednesdays, from the hub's target-data update (run by hand;
  its old schedule was 16:20 UTC, 9:20 AM in Arizona) until the submission
  pull request is open: by 8 PM Arizona time, 9 PM from 2026-11-04 to
  2027-03-10. Other days are free unless a note here says otherwise.
- App: answering your Submission note: admissions only this season,
  nothing more to build (Decided). That also settles your Open item, and
  three "Open items" in FLUSIGHT-2026-27.md (cards merged; rate-change and
  horizon -1; ED and peak targets).
- App: `app/tests/test_model_metadata.py` now handles `oneOf` (0e6e3cc).
  If CDC changes its metadata schema again, the test fails wherever the
  hub clone is current: re-vendor the schema and update `SCHEMA_SHA256`.
- Model: early-season Groundhog tails are wide (as-of 2026-09-26, US
  three weeks ahead: median 4,672, 0.99 quantile 90,434, from 2,515). No
  hub rule is near; no action asked.

## Open

- Open the hub pull request that brings both cards up to FluBNF's text
  (`designated_targets`, the zero-week sentence, versions 1.1 and 1.2)?
  Not needed for 2026-10-07.
- In that pull request, "Liu–West filter" for "particle filter" in the
  Oracle SIHRS card? The model lane's text; a test pins the phrase.
