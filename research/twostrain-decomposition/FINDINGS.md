# Two-strain member: the thin-data diagnosis is wrong

**Verdict: do not build candidate 4.1 as pre-registered. The typed-volume gate
keeps the cells where the member hurts and discards the ones where it helps.**

Run 2026-08-21 on the stored retrospectives (`app/state/retro_2s` vs
`app/state/retro_seal`), 15,357 cells paired on identical
(location, as-of, horizon), three seasons, frozen relWIS.

## What was tested

The memo ranked the two-strain member first on one causal claim: it failed on
the full grid *because* the NREVSS typed-lab channel was too thin to fund its
seven parameters, so gating on typed volume removes the failure. That predicts
the member does well where typed data is thick and badly where it is thin.

## What the data says

| where the cell sits | cells | states | WIS mass | two-strain | prod PF | delta |
| --- | --- | --- | --- | --- | --- | --- |
| ALL | 15,357 | 52 | 100% | 0.798 | 0.775 | +0.023 |
| own-state data, adequate (≥64 typed) | 6,196 | 39 | 43.1% | 0.758 | 0.701 | **+0.058** |
| own-state data, thin | 6,143 | 41 | 43.5% | 0.844 | 0.839 | +0.005 |
| HHS regional fallback | 3,018 | 19 | 13.4% | 0.775 | 0.803 | **−0.028** |

Lower relWIS is better, so a positive delta means the member is worse than the
production PF on those cells.

The prediction is inverted. The member's relative disadvantage is **largest**
where its own typed data is thickest (+0.058), it is a wash where the data is
genuinely thin (+0.005), and the only place it beats the PF is where it was
running on substituted regional data (−0.028).

By season, on the cells the gate would keep: 2023-24 −0.049, 2024-25 +0.092,
2025-26 +0.020. The single win is the plateau season and it does not replicate.

## The third class, which the gate cannot see

`flubnf/nrevss.py::a_share_series` falls back to the state's **HHS region**
when the state returns no rows or all-zero specimens. So states with no
clinical reporting were never running on thin data — they were running on a
neighbouring-states A/B mix labelled as their own, at high volume.

A volume-only gate marks those cells eligible, because the fallback series
looks thick: New York shows ~302 typed positives/week as of 2025-01-11, none
of it New York's. New York and Alaska are 100% fallback.

Grid composition: 40.2% own-state adequate, 39.8% own-state thin, 19.9%
fallback. The as-run gate (computed on the fed series, fallback included)
would pass 56.4% of state-weeks; a strict gate on own-state data only would
pass 40.2%. This partly reconciles the handoff's "~46 thin jurisdictions" at
the state-week level, but the reconciliation does not rescue the plan.

## What this does not prove

This is member-vs-member. A member worse than the PF alone can still earn a
seat by diversifying the ensemble, which is the actual shipping decision.
`ensemble_effect.py` tests that (2-member vs 3-member, equal weights, identical
cells, same classes) and **has not been run to completion** — the first attempt
was interrupted and wrote an empty frame, so it needs debugging before its
output means anything. Until then, "the gate does not do what it was supposed
to do" is established; "the member has no ensemble value" is not.

One narrower question stays alive: the member wins on fallback cells. But
inverting the rule into "seat it where the state has no data of its own" is
hard to justify mechanistically and would be fitting to this decomposition.
It needs the ensemble test and a mechanism story before it is worth anything.

## Reproducing

```
./.venv/bin/python -u research/twostrain-decomposition/decompose.py
```

Scores are cached in `paired_scores.csv`; delete it to re-score from samples.
Cell-level output is `cells.csv`. Classification reads the on-disk NREVSS
as-of cache (`app/state/nrevss`) directly and makes no network calls.

## Two process notes, both paid for

1. An earlier version of the classifier recursed through a monkeypatched
   `_abbr_for`, and its bare `except` turned the RecursionError into "thin
   data" for all 3,899 cells — a clean-looking table that was entirely
   artefact. The script now counts and prints classification failures and
   refuses to report when nothing classifies.
2. The same failure mode had already cost 44 minutes elsewhere that day: a
   Delphi probe swallowed HTTP 429s and reported rate-limiting as "no data."
   Any probe against an external API should fail loudly and batch its
   requests (`fluview_clinical` takes a comma-separated region list, turning
   a 624-request sweep into 3).
