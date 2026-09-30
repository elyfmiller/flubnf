# docs/: index by reader

Start with the [README](../README.md); each area of the tree has its own index linked from its Layout table.

| Reader | Doc | Covers |
|---|---|---|
| Students, first install | [INSTALL-STUDENTS.md](INSTALL-STUDENTS.md) | two files, two double clicks, no GitHub account; resetting or reinstalling, on macOS and on Windows |
| Anyone installing or updating | [LAUNCHERS.md](LAUNCHERS.md) | what each launcher and setup script does, who calls it, every `FLUBNF_*` variable |
| Getting the engine | [ENGINE.md](ENGINE.md) | the private PyBNF fork: archive, bundle or GitHub routes |
| Windows users | [WINDOWS.md](WINDOWS.md) | `setup.ps1`, `FluBNF.bat`, the particle-filter engine (install, updates, the production build, failures), when an update cannot go through, Controlled Folder Access, limitations |
| The mechanistic model | [ORACLE-SIHRS.md](ORACLE-SIHRS.md) | the Oracle SIHRS: filter plus the Oracle step, and its record |
| Students writing a model | [SANDBOX.md](SANDBOX.md) | the Sandbox: from an example or the template to a fitted model of your own |
| Model templates | [MODEL-PROVENANCE.md](MODEL-PROVENANCE.md) | SIHRS BNGL design history, sourced values, failed experiments |
| Replaying seasons | [RETROSPECTIVES.md](RETROSPECTIVES.md) | what a replay stores, archived runs, and exporting a replay to view on another machine |
| Missing weeks | [MISSING-DATA.md](MISSING-DATA.md) | how NHSN gaps and zeros appear in the hub, what each model does, the replay and the two off-by-default rules |
| Donor banks | [DONOR-BANKS.md](DONOR-BANKS.md) | the Groundhog's committed banks and how to reuse them ([data/README.md](../data/README.md)) |
| Changing the console's pages | [UI-KIT.md](UI-KIT.md) | the UI kit (tips, badges, alerts, empty states and the rest), when to use each, and each tab's stylesheet |
| Publishing | [SITE.md](SITE.md) | the public site generator (`flubnf site build`); not live yet |
| Submitting | [model-metadata/README.md](../model-metadata/README.md) | the hub model cards and IDs |
| The weekly rounds | [FLUSIGHT-2026-27.md](FLUSIGHT-2026-27.md) | the 2026-27 FluSight rules, the NAU_PyBNF models, the weekly routine, pitfalls and open decisions |
| Agents working on the project | [TEAM.md](TEAM.md) | who works on what, where each lane leaves context ([team/](team/README.md)), and the rules every lane follows |
| History | [archive/RELEASE-1.0.md](archive/RELEASE-1.0.md) | releases 1.0 and 1.1 (the retired blend); historical, not maintained |

The Groundhog has no doc of its own: the [README](../README.md) describes it, `flubnf/analogue.py` holds the method, and DONOR-BANKS.md the bank it splices in.
