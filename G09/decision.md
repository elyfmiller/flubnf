# G09: decision (by A)
Decision: A (both final votes A). Finishing the patch adds two checks
from B's tests:
- RE-06: the precise check of the card's Resume form (its hidden fields),
  and no Resume once nothing is added;
- RE-03: a `?rescore=1` visit while live starts no job either.
Implementer: A
Why: both votes agree on A. In the comparison, A's patch also fixes
RE-03 completely (criterion 1). B's patch keeps "Scoring failed…" on a
live replay whose weeks could score, and returns a 500 on a seal's page
while a replay runs over it. On RE-09, A reuses the existing tested
liveness check (criterion 4).
Left for Ely: none
Not reproduced: none
Merge: on origin/dev 68816e0, which has G08. G08's `usn.resolve` line
becomes `allow_aggregate=scoreable and not live`.
