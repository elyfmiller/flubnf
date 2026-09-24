# app/core/: the console's back end

One line per module, with the role tag its docstring opens with and its main callers (`server` is `app/ui/server.py`).

## Engines (`engines/`)

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `engines/pf.py` | SHIPPED | the Oracle SIHRS filter: writes `pf.conf`, runs PyBNF `fit_type=pf` in the engine venv, sharded; engine preflight | `retro`, `sandbox`, server, `flubnf/cli.py`, `flubnf/doctor.py` |
| `engines/analogue.py` | SHIPPED | the Groundhog: `flubnf.analogue` with the committed FluSurv-NET bank spliced in (`SHIPPED_AUX`) | `retro`, `groundhog`, server |
| `engines/profiles.py` | RESEARCH | COVID seam: pf's disease constants as functions of a `DiseaseProfile` | tests only |

## Storage and replay

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `retro.py` | PRODUCTION | season replay engine: calendar, sample store, run record, fit-level runner, scoring, finalize, archives | server Retrospective tab, `flubnf retro` |
| `runs.py` | PRODUCTION | run ledger, workroot leasing, seeds, run-display helpers | server, engines, `retro` |
| `knobs.py` | REGISTRY | every model tunable: shipped value read from its constant, bounds, members affected, card phrase; parse, digest, label (not read at run time yet) | `flubnf knobs` |
| `data.py` | PRODUCTION | vintage registry and hub freshness | server Data tab, `retro`, `scoring`, engines |
| `datasets.py` | RESEARCH | custom target data (MicroHub or hubverse CSV): validate, store under `app/state/datasets/`, FluSight-shaped locations and vintage CSVs | `flubnf dataset validate`; later stages |
| `horizons.py` | PRODUCTION | canonical vs stored horizon translation | `retro`, engines, `playback`, server |
| `playback.py` | PRODUCTION | season-player payloads and their cache | server `/api/retro/...`, `report_season`, `site_build` |
| `reclaim.py` | PRODUCTION | storage-reclaim policy | server Storage tab, `retro` |
| `ensemble.py` | PRODUCTION | samples to the 23 quantiles (blends nothing, despite the name) | `retro`, `playback`, server |
| `proc.py` | PRODUCTION | reduced-priority subprocess helpers | `engines/pf.py`, retro runners |
| `ttlcache.py` | PRODUCTION | short TTL cache for repeated filesystem scans | server |

## Scoring

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `scoring.py` | PRODUCTION | WIS scoring and the frozen cell rule | server, `retro`, `playback`, `site_build` |
| `relwis.py` | PRODUCTION | the two relWIS conventions and the convention note | server retro pages, `site_page`, `report_season` |
| `us_national.py` | PRODUCTION | US national resolution, labels, pooled-scope policy | every scoring surface |
| `categorical.py` | PRODUCTION | FluSight rate-change categories | `report`, server |
| `floor.py` | PRODUCTION | output floor on console-run PF samples | server `_run_all` |
| `completeness.py` | RESEARCH | reporting-completeness factors, reached only by research `spec.extra` keys | `engines/pf.py`, `engines/analogue.py` |

## Oracle step

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `oracle.py` | PRODUCTION | the Oracle step on the filter's samples (science in `flubnf/oracle*.py`) | `retro.run_week`, server `_run_all` |
| `oracle_text.py` | PAGE COPY | Oracle SIHRS sentences and record figures (Jinja global `oracle_text`) | server |
| `oracle_backfill.py` | VERIFICATION CLI ONLY | backfill a stored season into a new root, reproduce the screen | `flubnf oracle backfill` / `reproduce` |
| `submit.py` | PRODUCTION | hub submission CSVs and their validation | server `_run_all`, `oracle` |

## Reports

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `report_v2.py` | PRODUCTION | the weekly run report | server `_write_weekly_report`, `/output/report` |
| `report_season.py` | PRODUCTION | self-contained season HTML export | server `/retro/{season}/report` |
| `usmap.py` | PRODUCTION | build-time US map | `report_v2`, server home outlook, `site_build` |
| `report.py` | LEGACY | v1 tile-grid report; kept for the categorical shims | server, `site_build` |
| `groundhog.py` | RESEARCH CLI ONLY | analogue-alone season replays with coverage and bootstrap | `flubnf groundhog retro` |

## Public site

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `site_build.py` | PUBLIC SITE | what the site says: harvests state into `site/` | `flubnf site build` |
| `site_page.py` | PUBLIC SITE | how the site looks: one page, three tabs | `site_build` |

See [docs/SITE.md](../../docs/SITE.md).

## Sandbox

| Module | Tag | Role | Main callers |
|---|---|---|---|
| `sandbox.py` | SANDBOX | user models through the PF engine in `sandbox/` (the production preflight, `check` without the engine, stop, delete); examples from `flubnf/sandbox_examples/`; data from the hub or a `datasets.py` dataset | server `/sandbox` routes |
| `contactmap.py` | SANDBOX | contact map and reaction network from BNG2.pl, as SVG and graph JSON | server `/api/sandbox/models/...` |

`assets/states-albers-10m.json` is the US map geometry `usmap.py` draws.
