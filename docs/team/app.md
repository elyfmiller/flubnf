# App lane notes

The console, the launchers (FluBNF.command, FluBNF.app, FluBNF.bat,
setup.sh, setup.ps1), Windows, CI and the docs. Works on `dev`.

## Now

- 2026-09-30: `dev` equals `main` after PR #25 (Windows: the engine updates
  on every open, FluBNF in the Start menu, launcher fixes). CI runs on
  pushes to `dev` as well as on pull requests.

## Decided

- 2026-09-30: `flubnf engine-update` runs on every launcher open and only
  fast-forwards a clean checkout on `feature/particle-filter` to the pinned
  production commit (`app/core/engine_build.py`); it never resets, and
  leaves any other branch or edited checkout alone. Changing the production
  build means changing that pin.
- 2026-09-30: the first 3317 bytes of FluBNF.bat are frozen (a test pins
  their hash): an old copy that updates itself resumes at that offset.
  Edit below them only.

## For other lanes

- Engine (2026-09-30): your answer in engine.md is noted; the app lane
  changes nothing engine-related until the upstream `lwf` pull request is
  merged and the new pin is posted there.
- Submission: FluBNF produces `wk inc flu hosp` only (horizon -1 and the
  rate-change pmf behind knobs); no ED-visit, peak or sample output. Say so
  here if the team wants any of them for this season.

## Open

- Whether to add the ED-visit and peak targets this season.
