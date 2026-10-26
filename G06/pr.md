# G06 which-run-shows: PR (B)
PR: https://github.com/elyfmiller/flubnf/pull/55 (fix/G06-which-run-shows into dev)
Head: 5d1e564188c5c5db3e85b986d5fd14c32b85a0af (ac82edd the fix; 5d1e564 the Status cell)

Combined as decision.md says: A's patch as the base (OU-01, OU-02, OU-08,
OU-09, OU-11, the "Latest real-time run" label); HM-05 by B's
shared._wrote_forecasts (a "Both" run that wrote the Groundhog alone, a
record with no models table and one with no spec are never skipped) with
B's test beside A's; MO-06 adds the "Newer run on the Forecast tab" link
with B's assertions folded into A's test. The test_models_tab fakes take
the shipped rule's keywords (lambda **kw).

Checks: ruff clean; full suite 3492 passed, 154 skipped (the two Python
3.13 doctor checks, as on dev); invariance md5 56da9201b416eb5c80317c849b55168e
on both sides; live re-check on 8828 at desktop and phone, light and dark.
