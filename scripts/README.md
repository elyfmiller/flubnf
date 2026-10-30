# scripts/: ops scripts (not packaged)

Run from the repository root with the checkout's `.venv` (`data_audit.py` imports `flubnf`). No script imports another, and nothing imports these as a package.

| Script | What it does | Run as |
|---|---|---|
| `validate_submission.R` | **The authoritative hub check**: runs a submission through the hub's own `hubValidations` in a throwaway worktree of a hub clone; GREEN or RED | `Rscript scripts/validate_submission.R <file.csv> <hub_clone> [--window]` |
| `validate_submission.py` | thin Python wrapper around the R script | `python scripts/validate_submission.py <file.csv> <hub_clone> [--window]` |
| `sense_check.py` | **The pre-submission tail gate** (Spencer Fox's rule, 2026-10-21): the 97.5% quantile at each horizon over the recent level (mean of the last three reported weeks); FAIL, exit 1, when any horizon-3 ratio exceeds 30x; run on every file before the submission commit | `python scripts/sense_check.py <target-hospital-admissions.csv> <file.csv> [...] [--threshold 30]` |
| `dashboard_score.py` | **The weekly standing check**: reproduces the FluSight dashboard's scores from the hub's files (WIS per forecast against `target-data/oracle-output.csv`, scoringutils' pairwise relative WIS scaled to FluSight-baseline, natural and log scale); prints our two models' relative WIS, placement among this season's models, coverage, and the error split (spread against misses) for the national and state sets; `--dashboard` compares every model with the dashboard's published scores (a checkout of its `predevals/data` branch) and exits 1 on any difference | `python scripts/dashboard_score.py <hub_clone> <round> [<round> ...] [--dashboard <predevals_checkout>] [--cells <out.csv>]` |
| `cut_engine_archive.sh` | cuts the student engine archive `pybnf-pf-<sha>.tar.gz` from the PyBNF fork ([docs/ENGINE.md](../docs/ENGINE.md)) | `scripts/cut_engine_archive.sh [out-dir] [ref]` |
| `data_audit.py` | checks the hub archive for known data traps (vintage gaps, week-ending day, ...) | `python scripts/data_audit.py` |
| `make_dataset_template.py` | regenerates the synthetic grouped-CSV download template (`app/ui/static/dataset-template.csv`) and its two test slices (`app/tests/fixtures/grouped-template-*.csv`) from a fixed seed; `--check` only compares | `python scripts/make_dataset_template.py [--check]` |
| `macos/build_app_host.sh` | builds `FluBNF.app`'s host from `macos/flubnf_host.c` (with `macos/host_boot.py`) so the console window is FluBNF in the Dock; `setup.sh` and the launchers run it ([docs/LAUNCHERS.md](../docs/LAUNCHERS.md)) | `scripts/macos/build_app_host.sh [--force\|--check]` |
| `open_cycle.py` | opens and closes the real windowed app repeatedly and times each launch (GUI machine only) | `.venv/bin/python scripts/open_cycle.py [--cycles N] [--cold]` |
