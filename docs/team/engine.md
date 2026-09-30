# Engine lane notes

The private PyBNF fork, the Liu–West filter, and its port to public PyBNF.
Works on the lab Mac; its notes reach this file through Ely or another
lane.

## Now

- 2026-09-30: porting the filter to public lanl/PyBNF as
  `job_type = lwf` ("Liu–West Particle Filter", its own `filter` family,
  settings prefixed `lwf_`), agreed with the PyBNF maintainer, beside a
  later exact sampler, IBIS (lanl/PyBNF#973). Local branch
  `feat/particle-filter` of Ely's PyBNF fork, not pushed yet.

## Decided

- 2026-09-30: production keeps its own engine (`feature/particle-filter`
  2fdadee0) and the `pf_*` keys; rename nothing in FluBNF until the
  migration starts on purpose.
- 2026-09-30: say "Liu–West filter", and "forecasting sample" for its
  output, never "posterior". Once IBIS exists, never "particle filter"
  unqualified.
- 2026-09-30: choosing the jitter automatically by one-week-ahead score was
  tested and rejected (six states: relWIS 0.814 against 0.773 for a fixed
  0.15). Do not propose it again.
- Production SIHRS fits five parameters (Reff, eps1, phi1, mult, r); notes
  listing seven are stale.

## For other lanes

- App: the migration will need Python 3.12 or newer, `lwf_*` keys,
  edition-2 confs (`noise_model` and `random_seed` in place of
  `neg_bin_dynamic` and `pf_seed`; `pf_start_time` and
  `pf_sampling_interval` retired, gaps as explicit NaN rows), new output
  readers, and a statistical-equivalence check against the production
  record before switching (numbers will not be byte-identical).
- All: the private engine's `pf_continue` silently ignores revised earlier
  rows. Production refits every week, so it is safe; nothing that carries a
  swarm across weeks may rely on it.

## Open
