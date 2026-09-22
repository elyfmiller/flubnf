Hubverse model metadata for this team's FluSight entries, one YAML per model_id.

Team abbreviation is `NAU_PyBNF`, a new registration decided by the lead
on 2026-09-22. The hub builds a model_id as `<team_abbr>-<model_abbr>`, so
the hyphen is the separator and neither field may contain one: both must
match `^[a-zA-Z0-9_+]+$` and be at most 16 characters.

  NAU_PyBNF-OracleSIHRS.yml   the SIHRS particle filter, designated
  NAU_PyBNF-GroundHogCGR.yml  the Groundhog, designated

Two models, submitted separately, nothing blended. The Oracle SIHRS is the
mechanistic model; its parameterisation from past seasons is where the
information the retired blend used to add now lives, and the card's
`methods_long` is marked PENDING until the team building that
parameterisation has written it. The Groundhog is the calendar analogue
that was the blend's empirical member, with a committed FluSurv-NET donor
bank spliced in. Both are designated: a team may designate at most two
models, and designation makes a model eligible for the hub ensemble and
the public visualisation.

The previous registration, `LosAlamos_NAU`, submitted from 2023 through
2026-09: `LosAlamos_NAU-CModel_Flu` (the equal-weight blend, designated,
version 3.0) and `LosAlamos_NAU-SIHRS` (the mechanistic member alone,
undesignated). Those cards and their scoring history stay on the hub under
that team; nothing carries over to the new identities, which the hub sees
as new models. The PIs' 2026-08-27 decision to keep the old registration
was reversed with the blend it carried. The old cards are in this
repository's history (`git log -- model-metadata/`), not in this
directory, because the drift test below requires every card here to carry
this team's abbreviation.

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
