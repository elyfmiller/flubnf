# flubnf/templates/: BNGL model templates

The production model is `SIHRS_pop_min.bngl`, not `SIHRS_pop.bngl`; design history and sources for every SIHRS file are in [docs/MODEL-PROVENANCE.md](../../docs/MODEL-PROVENANCE.md). Paths here are hardcoded in code and tests, so do not rename them.

| Template | Role | Fitted (`*__FREE`) | Used by | Pinned by |
|---|---|---|---|---|
| `SIHRS_pop_min.bngl` | production: the Oracle SIHRS filter | Reff, eps1, phi1, mult, r | `app/core/engines/pf.py` (`TEMPLATE`), `flubnf/profiles.py` (influenza), `app/core/site_build.py` (published verbatim), `/model/pf` in `app/ui/server.py`, `scripts/vintage_run.py`, `scripts/rt_prior_run.py` | `tests/test_min_template.py`, `tests/test_profiles.py`, `app/tests/test_natgrowth.py`, `app/tests/test_pages.py` |
| `SIHRS_pop_2strain_min.bngl` | research: two-strain (A/B) PF variant, failed its gate, off the nav | ReffA, ReffB, eps1, phi1A, phi1B, mult, r | `pf.py` (`TEMPLATE_2S`, `variant=2strain`), `/model/pf2s` | `app/tests/test_pages.py` |
| `SIHRS_pop_natg.bngl` | research: `min` plus a national-growth factor | as `min` | `pf.py` (`TEMPLATE_NATG`, `variant=natg`), `flubnf/natgrowth.py` | `app/tests/test_natgrowth.py` |
| `SIHRS_pop_covid.bngl` | research: COVID port, `omega` fitted | as `min` + omega | `flubnf/profiles.py` (COVID profile) | `tests/test_engine_profiles.py` |
| `SIHRS_pop.bngl` | research: multi-season 8-parameter model | Reff, eps1, phi1, eps2, phi2, mult, impr, r | `scripts/profiled_fit_run.py` (`TEMPLATE`, re-exported to the other research scripts) | `tests/test_min_template.py` (full reference), `tests/test_particle_filter.py`, `tests/test_sihrs_anchor.py` |
| `SIHRS_pop_cart.bngl` | research: `SIHRS_pop.bngl` with Cartesian harmonics; no runtime path | Reff, a1, b1, a2, b2, mult, impr, r | none (`flubnf/seasonal.py` cites it) | `tests/test_seasonal.py` |
| `Alabama.bngl` | legacy: piecewise SIR of the workspace CLI | I0, b0, gamma, mult, r, t0 | `flubnf/config.py` default, `flubnf init` / `update-files` / `backtest` | `tests/test_bngl_files.py` |
| `AlabamaSIRS.bngl` | legacy: smooth-beta SIRS of the workspace CLI | I0, b0, db1, gamma, mult, r | `flubnf/config.py` default when `model_type = sirs_logistic` | `tests/test_bngl_files.py` (SIRS cases) |
| `Alabama.conf` | legacy: PyBNF config template for the workspace CLI | | `flubnf/config.py` default, `flubnf/conf_files.py`, `flubnf/backtest.py` | `tests/test_conf_files.py` |

`{{TOKEN}}` placeholders are per-state data filled by `flubnf/sihrs_fit.py` (`materialize_model`); an unresolved token raises. The Sandbox's own example models are in `flubnf/sandbox_examples/`, not here.
