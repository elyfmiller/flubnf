# docs/: index by reader

Start with the [README](../README.md); each area of the tree has its own index linked from its Layout table.

| Reader | Doc | Covers |
|---|---|---|
| Students, first install | [INSTALL-STUDENTS.md](INSTALL-STUDENTS.md) | one line or one clone, one double click, no GitHub account and no engine file; where it lands; a first forecast; the private engine when the lab asks for it; resetting or reinstalling, on macOS and on Windows |
| Anyone installing or updating | [LAUNCHERS.md](LAUNCHERS.md) | what each launcher and setup script does, who calls it, what the one-line reinstall moves where, every `FLUBNF_*` variable |
| Getting the engine | [ENGINE.md](ENGINE.md) | the public engine, public PyBNF, the default, which installs itself; choosing the private engine, the lab's PyBNF fork, the fallback; its archive, bundle or GitHub routes; which build is running |
| Windows users | [WINDOWS.md](WINDOWS.md) | `setup.ps1`, `FluBNF.bat`, the particle-filter engine (the public engine, the private fallback, install, updates, the production build, failures), when an update cannot go through, Controlled Folder Access, limitations |
| Outside groups and other targets | [ADAPTING.md](ADAPTING.md) | what works today, with no code, for your own weekly data and for another target, pathogen, geography or season calendar; what the console assumes; what needs code |
| The mechanistic model | [ORACLE-SIHRS.md](ORACLE-SIHRS.md) | the Oracle SIHRS: filter plus the Oracle step, and its record |
| Students writing a model | [SANDBOX.md](SANDBOX.md) | the Sandbox: from an example or the template to a fitted model of your own |
| Students working from a terminal, and proposing a model | [CONTRIBUTING.md](CONTRIBUTING.md) | the `model`, `experiment` and `storage` commands (JSON, exit codes), a clone on the Mac Studio, a fork and a branch, a proposal, its pull request and what CI refuses |
| Model templates | [MODEL-PROVENANCE.md](MODEL-PROVENANCE.md) | SIHRS BNGL design history, sourced values, failed experiments, the engine of record |
| Replaying seasons | [RETROSPECTIVES.md](RETROSPECTIVES.md) | what a replay stores, archived runs, resuming across engines, and exporting a replay to view on another machine |
| Missing weeks | [MISSING-DATA.md](MISSING-DATA.md) | how NHSN gaps and zeros appear in the hub, what each model does, the replay and the two off-by-default rules |
| Donor banks | [DONOR-BANKS.md](DONOR-BANKS.md) | the Groundhog's committed banks and how to reuse them ([data/README.md](../data/README.md)) |
| Changing the console's pages | [UI-KIT.md](UI-KIT.md) | the UI kit (tips, badges, alerts, empty states and the rest), when to use each, and each tab's stylesheet |
| Publishing | [SITE.md](SITE.md) | the public site generator (`flubnf site build`); not live yet |
| Submitting | [model-metadata/README.md](../model-metadata/README.md) | the hub model cards and IDs |
| The weekly rounds | [FLUSIGHT-2026-27.md](FLUSIGHT-2026-27.md) | the 2026-27 FluSight rules, the NAU_PyBNF models, the weekly routine, pitfalls and open decisions |
| The maintainers (Ely's lanes) | [TEAM.md](TEAM.md) | who works on what, where each lane leaves context ([team/](team/README.md)), and the rules every lane follows |
| History | [archive/RELEASE-1.0.md](archive/RELEASE-1.0.md) | releases 1.0 and 1.1 (the retired blend); historical, not maintained |

The Groundhog has no doc of its own: the [README](../README.md) describes it, `flubnf/analogue.py` holds the method, and DONOR-BANKS.md the bank it splices in.
