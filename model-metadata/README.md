Hubverse model metadata for this team's FluSight entries, one YAML per model_id.

Team abbreviation is `LosAlamos_NAU`, the registration this group has held
on the hub since 2023. The hub builds a model_id as
`<team_abbr>-<model_abbr>`, so the hyphen is the separator and neither field
may contain one: both must match `^[a-zA-Z0-9_+]+$` and be at most 16
characters.

  LosAlamos_NAU-CModel_Flu.yml   the shipped 50/50 blend, designated
  LosAlamos_NAU-SIHRS.yml        the mechanistic member, undesignated

Why the existing registration rather than a new team (PIs' decision,
2026-08-27): the slot, its scoring history and its contributor list carry
forward, and `CModel_Flu` remains an honest name for what the flagship is.
Version 3.0 of that model is the same compartmental line with two changes
stated in `methods_long` -- the transmission parameters are now estimated by
a sequential particle filter rather than batch adaptive MCMC, and the
submitted forecast blends that model with an empirical companion. Changing a
model's method between seasons and recording it in `model_version` is the
ordinary hubverse practice; it is not a new model identity.

Only the ensemble is designated. A team may designate at most two models,
and designation makes a model eligible for the hub ensemble and the public
visualisation. The two members correlate closely, so designating both would
contribute two near-duplicate forecasts to the hub ensemble as though they
were independent. The member is still submitted, scored and archived; it
simply does not feed the blend.

`app/core/submit.py` holds `TEAM_ABBR` and `MODEL_ABBR` as constants
(model-metadata/ is not packaged into the wheel, so a submission cannot
depend on reading these files at run time). `app/tests/test_submit_join.py`
parses both YAMLs and asserts those constants verbatim, so the two cannot
drift apart.

Validate against the hub's own schema before opening a pull request:

  hub-config/model-metadata-schema.json
