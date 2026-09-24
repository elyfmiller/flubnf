Hubverse model metadata for this team's FluSight entries, one YAML per model_id.

Team abbreviation is `NAU_PyBNF`, a new registration decided by the lead
on 2026-09-22. The hub builds a model_id as `<team_abbr>-<model_abbr>`, so
the hyphen is the separator and neither field may contain one: both must
match `^[a-zA-Z0-9_+]+$` and be at most 16 characters.

  NAU_PyBNF-OracleSIHRS.yml   the Oracle SIHRS (the particle filter plus the Oracle step), designated
  NAU_PyBNF-GroundHogCGR.yml  the Groundhog, designated

Two models, submitted separately. The Oracle SIHRS is the mechanistic
model: the SIHRS compartment model fitted weekly by the particle filter,
plus a post-fit step that blends each stored forward sample's growth with
one donor growth path from an earlier season at the same calendar week
(docs/ORACLE-SIHRS.md); its card's `methods_long` describes both, carries
the frozen pre-registration's hash, and carries verbatim the donor-bank
sentence of `app/core/oracle_text.BANK_TEXT["card"]` (the one marked place
for which data streams form the pool; the test holds the two equal). The
Groundhog is the calendar analogue with a committed FluSurv-NET donor bank
spliced in. Both are designated: a team may designate at most two models,
and designation makes a model eligible for the hub ensemble and the public
visualisation.

The previous registration, `LosAlamos_NAU`, submitted from 2023 through
2026-09 (`LosAlamos_NAU-CModel_Flu` and `LosAlamos_NAU-SIHRS`). Those
cards and their scoring history stay on the hub under that team; nothing
carries over to the new identities, which the hub sees as new models. The
old cards are in this repository's history, not in this directory, because
the drift test below requires every card here to carry this team's
abbreviation.

`app/core/submit.py` holds `TEAM_ABBR`, `MODEL_ABBR` and `RETIRED_ABBR` as
constants (model-metadata/ is not packaged into the wheel, so a submission
cannot depend on reading these files at run time).
`app/tests/test_submit_join.py` parses every YAML here and asserts that the
written and the retired identities together are exactly the registered
cards, so the two cannot drift apart.

Joining the hub as a new team is the metadata pull request itself: both
cards added to `model-metadata/` of cdcepi/FluSight-forecast-hub before the
first `model-output/NAU_PyBNF-<model>/` file. The hub's READMEs name no
other registration step; the FluSight contact is flusight@cdc.gov.

Validate against the hub's own schema before opening a pull request:

  hub-config/model-metadata-schema.json

`app/tests/test_model_metadata.py` does that on every run: it validates
both cards against `app/tests/hub_model_metadata_schema.json`, a byte copy
of that schema (sha256 7fb27f66e7e2a573, checked against the hub clone
whenever one is present), including the 200-character limit on `methods`.

A submission CSV is checked the way the hub's CI checks it, with the hub's
own hubValidations R package, by `scripts/validate_submission.R` (or its
Python wrapper `scripts/validate_submission.py`). It copies the matching
card from this directory into a throwaway worktree of the hub clone when
the hub does not carry it yet.
