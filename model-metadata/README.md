Hubverse model metadata for this team's FluSight entries, one YAML per model_id.

Team abbreviation is `LosAlamos_NAU`, the registration this group has held
on the hub since 2023. The hub builds a model_id as
`<team_abbr>-<model_abbr>`, so the hyphen is the separator and neither field
may contain one: both must match `^[a-zA-Z0-9_+]+$` and be at most 16
characters.

  LosAlamos_NAU-SIHRS.yml         the SIHRS particle filter, submitted
  LosAlamos_NAU-GroundhogCGR.yml  the Groundhog, submitted
  LosAlamos_NAU-CModel_Flu.yml    the retired 50/50 blend, still designated

Since 2026-09-22 the project ships two standalone models and no blend. The
SIHRS is the mechanistic model; its parameterisation from past seasons is
where the information the blend used to add now lives. The Groundhog is
the calendar analogue that was the blend's empirical member, with an
auxiliary FluSurv-NET donor bank spliced in, and it takes the calendar's
place as its own submission. `CModel_Flu`, the blend, is not written any
more; its card stays here because the hub keeps that model's history.

Why the existing registration rather than a new team (PIs' decision,
2026-08-27): the slot, its scoring history and its contributor list carry
forward. Changing a model's method between seasons and recording it in
`model_version` is the ordinary hubverse practice; it is not a new model
identity.

Designation is open. A team may designate at most two models, and
designation makes a model eligible for the hub ensemble and the public
visualisation. `CModel_Flu` holds the designated slot and no longer
submits; whether that slot moves to the SIHRS (as `CModel_Flu` version
4.0, the same compartmental line under the registered flagship identity),
whether the Groundhog is designated beside it, or whether both new models
stay undesignated is the PIs' decision and is not encoded here. Until it
is made, both submitted cards say `designated_model: false`.

`app/core/submit.py` holds `TEAM_ABBR`, `MODEL_ABBR` and `RETIRED_ABBR` as
constants (model-metadata/ is not packaged into the wheel, so a submission
cannot depend on reading these files at run time).
`app/tests/test_submit_join.py` parses every YAML here and asserts that the
written and the retired identities together are exactly the registered
cards, so the two cannot drift apart.

Validate against the hub's own schema before opening a pull request:

  hub-config/model-metadata-schema.json
