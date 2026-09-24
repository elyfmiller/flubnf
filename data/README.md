# data/: committed donor banks

`data/banks/` holds past-season surveillance committed to the repository, so a fresh clone forecasts offline and every run records which bank it used ([docs/DONOR-BANKS.md](../docs/DONOR-BANKS.md)).

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
