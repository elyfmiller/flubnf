Hubverse model metadata for this team's FluSight entries, one YAML per model_id.

Team abbreviation is `NAU_FluBNF`. The hub builds a model_id as
`<team_abbr>-<model_abbr>`, so the hyphen is the separator and neither field
may contain one: both must match `^[a-zA-Z0-9_+]+$` and be at most 16
characters.

  NAU_FluBNF-ensemble.yml   the shipped 50/50 blend, designated
  NAU_FluBNF-SIHRS.yml      the mechanistic member, undesignated

Only the ensemble is designated. A team may designate at most two models, and
designation makes a model eligible for the hub ensemble and public
visualisation. The two members correlate closely, so designating both would
contribute two near-duplicate forecasts to the hub ensemble. The member is
still submitted, scored and archived; it simply does not feed the blend.

Validate against the hub's own schema before opening a pull request:

  hub-config/model-metadata-schema.json

in a local clone of cdcepi/FluSight-forecast-hub.
