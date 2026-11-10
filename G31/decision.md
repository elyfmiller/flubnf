# G31: decision (by A)
Decision: combined: A's patch (proto/G31-A), with two parts from B's:
- SB-25: B's `_weeks(n, what)` helper in the three notices (fill, its dropped weeks, simulate), in place of the inline singulars.
- SB-26: the runner messages' cap at the last 64 KB (B's), not 256 KB.
Everything else is A's:
- SB-07: `rules`, `reactions`, `VIEW_VERSION` 3, and the Model view's svg label.
- SB-18: data.exp saved when edited but never named.
- SB-19: the plain headline, and the pointer only when the page shows its notice.
- SB-20.
- SB-21: lower-case labels, 10,000, "as written".
- SB-22: `shipped_state["dataset"]`, Donors in words, no w stat.
- SB-23, SB-24.
- UI-16.
- UI-19: the `bounds` rename and `textScale()`.
Tests: A's test_sandbox_polish.py with B's tests for the helper and the cap folded in, and the pins both sides moved.
Implementer: A (the decider; the solutions are combined)
Why: the votes agree on combine and on every part.
- Criterion 1: A's version bump redraws a model cached before the fix, and A's UI-19 fixes the drawing's own width (the `box` helper hoisting over the parameter), where B's would add a sideways scroll to a desktop card.
- Criterion 2: A's keeps an edited data.exp, which Simulate and Fill read from disk; and A's pointer names where the notice actually is.
- Criterion 4: B's `_weeks` helper is the smaller form for three messages; 64 KB is enough of an engine log for a student's zip.
Left for Ely: none
Not reproduced: none
