# flubnf/templates/: BNGL model templates

The production model is `SIHRS_pop_min.bngl`, not `SIHRS_pop.bngl`; design history and sources for every SIHRS file are in [docs/MODEL-PROVENANCE.md](../../docs/MODEL-PROVENANCE.md). Paths here are hardcoded in code and tests, so do not rename them.

| Template | Role | Fitted (`*__FREE`) | Used by | Pinned by |
|---|---|---|---|---|
| `SIHRS_pop_min.bngl` | production: the Oracle SIHRS filter | Reff, eps1, phi1, mult, r | `app/core/engines/pf.py` (`TEMPLATE`), `app/core/site_build.py` (published verbatim), `/model/pf` in `app/ui/routes/models.py` | `tests/test_min_template.py`, `app/tests/test_natgrowth.py`, `app/tests/test_pages.py` |
| `SIHRS_pop_2strain_min.bngl` | research: two-strain (A/B) PF variant, failed its gate, off the nav | ReffA, ReffB, eps1, phi1A, phi1B, mult, r | `pf.py` (`TEMPLATE_2S`, `variant=2strain`), `/model/pf2s` | `app/tests/test_pages.py` |
| `SIHRS_pop_natg.bngl` | research: `min` plus a national-growth factor | as `min` | `pf.py` (`TEMPLATE_NATG`, `variant=natg`), `flubnf/natgrowth.py` | `app/tests/test_natgrowth.py` |
| `SIHRS_pop.bngl` | research: multi-season 8-parameter model | Reff, eps1, phi1, eps2, phi2, mult, impr, r | none at runtime (reference) | `tests/test_min_template.py` |

`{{TOKEN}}` placeholders are per-state data filled by `flubnf/sihrs_fit.py` (`materialize_model`); an unresolved token raises. The Sandbox's own example models are in `flubnf/sandbox_examples/`, not here.

Removed templates: git history and lab archive.
