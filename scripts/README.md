# scripts/: ops and research scripts (not packaged)

Run from the repository root; the Python scripts import `scripts.*` (hence `__init__.py`) and `flubnf`.

## Ops

| Script | What it does | Run as |
|---|---|---|
| `validate_submission.R` | **The authoritative hub check**: runs a submission through the hub's own `hubValidations` in a throwaway worktree of a hub clone; GREEN or RED | `Rscript scripts/validate_submission.R <file.csv> <hub_clone> [--window]` |
| `validate_submission.py` | thin Python wrapper around the R script | `python scripts/validate_submission.py <file.csv> <hub_clone> [--window]` |
| `cut_engine_archive.sh` | cuts the student engine archive `pybnf-pf-<sha>.tar.gz` from the PyBNF fork ([docs/ENGINE.md](../docs/ENGINE.md)) | `scripts/cut_engine_archive.sh [out-dir] [ref]` |
| `data_audit.py` | checks the hub archive for known data traps (vintage gaps, week-ending day, ...) | `python scripts/data_audit.py` |
| `make_dataset_template.py` | regenerates the synthetic grouped-CSV download template (`app/ui/static/dataset-template.csv`) and its two test slices (`app/tests/fixtures/grouped-template-*.csv`) from a fixed seed; `--check` only compares | `python scripts/make_dataset_template.py [--check]` |
| `open_cycle.py` | opens and closes the real windowed app repeatedly and times each launch (GUI machine only) | `.venv/bin/python scripts/open_cycle.py [--cycles N] [--cold]` |

`flubnf validate-submission` (`flubnf/validate.py`) is the legacy CLI's in-Python schema check, not the hub's code; use the R script before submitting.

## Research (AMCMC-era harnesses; outputs go to `backtest_results/`)

| Script | What it does | Imports |
|---|---|---|
| `profiled_fit_run.py` | fit with `mult` profiled out; also the shared config (`HUB`, `TRUTH`, `LOCS`, `PYBNF`, `BNG`, `TEMPLATE`) | `flubnf/profile_mult.py`, `SIHRS_pop.bngl` |
| `vintage_run.py` | fit on each as-of vintage, score against settled truth; exports `vintage_for`, `MIN_TEMPLATE` | `profiled_fit_run` |
| `rt_prior_run.py` | SIHRS fit with a calendar-conditioned prior on Reff | `profiled_fit_run`, `vintage_run` |
| `pf_run.py` | scores the in-Python particle filter and picks its `jitter` without selection bias | `profiled_fit_run`, `vintage_run`, `anchor_analysis` |
| `anchor_analysis.py` | held-out validation of anchor and damp; library for `pf_run.py` | reads `backtest_results/anchor_validation.json` |

`profiled_fit_run.py` and `anchor_analysis.py` read the hub from `FLUSIGHT_HUB`, not `FLUBNF_HUB`. `tests/test_worker_options.py` parses `vintage_run.py` and `rt_prior_run.py`.
