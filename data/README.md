# data/: committed donor banks and truth snapshots

`data/banks/` holds past-season surveillance committed to the repository, so a fresh clone forecasts offline and every run records which bank it used ([docs/DONOR-BANKS.md](../docs/DONOR-BANKS.md)). `data/vintages/` holds the truth snapshots for the weeks the hub archive skipped (second section).

| File | What | Used by |
|---|---|---|
| `banks/flusurv.json` | FluSurv-NET hospitalization-rate donor bank (Delphi `flusurv`) | the Groundhog (`SHIPPED_AUX`, `app/core/engines/analogue.py`) and the Oracle SIHRS donor mix (`flubnf/oracle_mix.py`) |
| `banks/flusurv.manifest.json` | source, build time, epiweek span, locations, cell count, content digest | `flubnf/bank.py` |
| `banks/iliplus.json` | ILI+ donor bank (Delphi `fluview`) | research presets only (`app/core/engines/analogue.py` `AUX_PRESETS`) |
| `banks/iliplus.manifest.json` | as above | `flubnf/bank.py` |

Every read goes through `flubnf/bank.py`, which checks the manifest digest and raises on a missing or mismatched bank; nothing falls back silently. The digest covers content, not bytes, so reformatting a bank is harmless.

| Command | Does |
|---|---|
| `flubnf bank show <stream>` | prints the manifest, digest verified |
| `flubnf bank verify <stream>` | rebuilds from Delphi and reports what moved |
| `flubnf bank build <stream> [--out DIR]` | rebuilds and writes the bank and manifest; commit both |

`data/covidhub/` and `data/historical_priors/`, if present, are leftovers of removed code (the COVID research cache and the legacy workspace CLI); nothing creates them now.

# data/vintages/: shipped truth snapshots

Retrospectives replay a season week by week, and each week reads the hub's dated truth vintage `auxiliary-data/target-data-archive/target-hospital-admissions_<Saturday>.csv`. The hub keeps that archive by hand and skipped eight weeks that FluSight scored. The published file for each of those weeks exists in the hub's commit history; `data/vintages/` holds those files, bytes unchanged, renamed to the archive's naming, so a shallow hub clone (the one `setup.sh` makes) replays every scored week.

| As-of week | Reference date | Season | Hub commit |
|---|---|---|---|
| 2024-11-23 | 2024-11-30 | 2024-25 | `1c8e1141` |
| 2024-12-07 | 2024-12-14 | 2024-25 | `47f76990` |
| 2025-01-04 | 2025-01-11 | 2024-25 | `fd7109e8` |
| 2025-11-22 | 2025-11-29 | 2025-26 | `03a4b119` |
| 2025-12-20 | 2025-12-27 | 2025-26 | `42ee35f1` |
| 2026-01-31 | 2026-02-07 | 2025-26 | `569f578a` |
| 2026-03-07 | 2026-03-14 | 2025-26 | `f696cda5` |
| 2026-04-25 | 2026-05-02 | 2025-26 | `6c25e693` |

`manifest.json` records, per file, the as-of week, reference date, season, hub commit (short and full SHA, commit date), source path (`target-data/target-hospital-admissions.csv`), sha256, row count and location count. Every read goes through `app.core.data.vintage_path`, which takes the hub archive's file when it exists, else the shipped one after checking its sha256 against the manifest; a mismatch raises, nothing falls back silently (`flubnf/vintages.py`, the rule `flubnf/bank.py` applies to the donor banks). `data.vintages()` lists the union of the two folders, so the season week lists, the Data tab, the engines and the scorer see the same weeks. The shipped files differ from the archive's only in formatting (dates unquoted); every reader parses them with pandas or csv.

A filled week is replayed and scored like any other: against the settled truth, relative to the FluSight baseline submitted for that reference date. The player and the season report caption such a week with its source ("data: hub snapshot, commit 1c8e1141"), and the Data tab marks it as a shipped snapshot.

Two weeks have no published data anywhere and no FluSight round, so there is nothing to fill and nothing to score: as-of 2024-05-04 (reference 2024-05-11; HHS hospital reporting ended) and as-of 2025-01-18 (reference 2025-01-25; federal communications pause). The manifest lists them under `no_data_weeks`; the player and the season report show a placeholder for them ("No data published; no FluSight round this week") instead of skipping the date.

A replay finished before these files were added has fewer weeks than the season now lists. The season page and the retrospectives list say how many weeks were added; Run resumes the season and runs only those weeks. A sealed record cannot be resumed and needs a fresh replay to include them.
