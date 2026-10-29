# G11: compare (A)

B's patch applied on 368e922 (scratch worktree), served on 8817, with my
tests run against it and B's against mine.

| Bug | A's | B's | Better, and why |
|---|---|---|---|
| HM-01 (MO-01, ME-01) | the shipped row on all three pages; bars against "Without size-matched donors" 0.660; the Record line names 0.660 and the pooled 0.670; README parser reads three rows by their leads | the same, bar "Without the size-matched donors"; the Record line names 0.660 only | Equal. Same root cause found (the parser kept the replaced row) and the same fix. B's Record line is shorter; mine keeps the pooled form the line named before. Either is fine. |
| ME-02 (MO-02) | "within each half, donor weeks whose count is near the jurisdiction's newest count carry the most weight (since 2026-10-23), with equal weights when that would leave fewer than 30 effective donors"; a "Favoured: own and similar-sized weeks" fact on the model page; no new Methods tile | "inside each pool … with 30 effective donors as the floor"; a new Methods tile "Weeks sized like the newest · most of the weight" | **A**, criterion 1. The kernel works inside each half of the admissions pool (the card: "Within each half"). "Inside each pool" reads as if it reached the FluSurv-NET pool, which stays pooled. "30 effective donors as the floor" is not what the guard does: below 30 it drops the kernel and weights equally, as mine says. The new tiles are a wash: one fact each, in different places. |
| ME-11 | own share: "…; 0 drops it." Bank help unchanged: in the console, none IS the bare analogue (a run with the bank at none records no aux_pools and no local_pools; `_run_extra` adds local_pools only with a bank; G03 greys out own share and kernel), so that half does not reproduce | own share: "…; 0 drops the own-state weighting." (99 characters); bank: "none runs without a bank." | **A** on the bank, criterion 2: B's changes a help line that is right, and drops what none means. On own share both are right; B's is clearer, mine shorter. I'd accept B's own-share words. |
| ME-17 | `methods._choice` skips the "(value)" when the word already starts with it; the panel's option and the run's settings still read "none (bare analogue)" | CHOICE_WORDS "none" becomes "none" | **A**, criterion 2. B's changes the panel's option and every run's settings words, beyond Methods' range. The bug is the doubled parenthesis on one page. `_choice` keeps "(value)" for every other choice ("expected total (early season) (season_total_early)" still passes test_fewer_marks on mine). |
| ME-23 | "donor week" in the title, the aria-label and the comment | the same | Equal, but B's patch leaves test_console_qol's pin of the old aria-label ("Each donor season contributes"), so test_diagram_crops_and_labels fails on it (IndexError). I updated that pin. |
| MO-15 | the fan ends at x 487, spread kept (96 to 190) | ends at 487, spread scaled to the shorter reach (118 to 164) | Equal. B's keeps the old wedge's angle; mine stays readable as a fan at 390. Either. |

Tests run cross-wise: B's tests pass on mine except where they pin B's own
words (the bank help, the "none" word, the Methods tile). Mine fail on B's
in the same way, plus test_console_qol above.

Full suite on mine: 3537 passed, 155 skipped, 0 failed.

Vote: A. Optional from B: the own-state help "0 drops the own-state
weighting." (B's words, 99 characters).
