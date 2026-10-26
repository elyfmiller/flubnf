# The historical ceiling on the Groundhog's retro seasons (2026-10-25)

Model lane (laptop). The full record of the screen summarised in
[model.md](../model.md) (entry of 2026-10-25, 23:50 UTC, laptop): the
historical ceiling, knob `output.tail_hist` at the maximum, as a
post-calibration step on the Groundhog's own retro in the shipped kernel
form, with the ratios from each week's vintage. A copy of the lab archive
`FluBNF-local/research/groundhog-hist-ceiling/`, without the per-cell score
files (results/, about 13 MB).

| File | What it is |
|---|---|
| [prereg.txt](prereg.txt) | the pre-registration, frozen 2026-10-25 23:40 UTC before any replay or score; `shasum -a 256 -c prereg.txt.sha256` checks it (c9587ab5...) |
| [report.txt](report.txt) | the pre-registered report as `hist.py --report` printed it: the reproduction gate, every arm by season and as-of month with coverage, the bootstrap, the touched blocks, the ceiling's ratios, the h3 tails, the predictions G1 to G6 and the decision rule |
| [RUNLOG.md](RUNLOG.md) | what ran, in order, with the checks read after the scores (the 2024-25 cancellation, the size of the clip, the vintage against the final truth, the October maxima and where they come from, the week-53 window) |
| [run_kernel.py](run_kernel.py), [run_all.sh](run_all.sh) | the replay: the shipped kernel form over every vintage of 2023-24 to 2026-27, the quantiles stored |
| [hist.py](hist.py) | the post-calibration arms in the pipeline's order (hub rows, the ceiling, the n-cap) through the repository's own functions, the scoring and the report |
| [xcheck.py](xcheck.py) | the code check: the ratios re-implemented from the written rule and compared with `flubnf.tailcap.history_ratios` on every replay week |

Ran on dev fafa1db (merge 463ddba, the ceiling) with the hub mirror at
3a83d410, from a scratch worktree; the scripts import the repository and
take `PYTHONPATH` (the checkout) and `FLUBNF_HUB` (the hub mirror) from the
environment, as `run_all.sh` sets them.

Result in one line: the pairing (the maximum, then the shrink at 15x)
passes every pre-registered test for the Groundhog, and it is free rather
than a gain: -0.0013 [-0.0039, +0.0009] against the shrink alone over the
three seasons, all of it from December 2023, and +0.0015 in 2023-24's
October weeks. The code check found no defect in what the ceiling
computes; the three findings for the Submission lane (the week-53 window,
the unrecorded skip, the 2024 voluntary window in the history) are in
model.md under For other lanes, 2026-10-26.
