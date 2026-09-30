# App lane notes

The console, the launchers (FluBNF.command, FluBNF.app, FluBNF.bat,
setup.sh, setup.ps1), Windows, CI and the docs, and the shared context
pages (TEAM.md, team/README.md, FLUSIGHT-2026-27.md). Works on `dev`.

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
- Submission (2026-09-30): your answer is noted: admissions only this
  season, nothing more to build. FLUSIGHT-2026-27.md now lists the scope,
  the designation and the hub cards as decided.

- Model (2026-09-30): both App items done: FLUSIGHT-2026-27.md no longer
  calls the card's wording stale, and it gives the in-app replay figures
  beside the pre-registration ones. The spelling is "Liu-West" with a
  hyphen, as in the code and the card (the repository's text rule bans en
  dashes); TEAM.md, team/README.md, this file and FLUSIGHT-2026-27.md now
  use it.
- Engine, Submission (2026-09-30): please spell it "Liu-West" (hyphen) in
  engine.md and submission.md too; the en dash is out under the text rule.

## Open
